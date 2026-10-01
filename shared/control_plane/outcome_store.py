"""Artifact review adapter; review, audit and work-item metadata share one UOW."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .domain.execution_policy import ExecutionDenied
from .domain.outcome_acceptance import validate_outcome
from .domain_records import agent_run_record, artifact_record, work_item_record
from .models import AuditEvent
from .outcome_models import OutcomeAcceptanceTable
from .run_evidence import hash_evidence
from .tables import AgentRunTable, ArtifactTable, CompanyContextTable, WorkItemTable


class SqlAlchemyOutcomeStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def review(
        self,
        *,
        company_id: str,
        work_item_id: str,
        artifact_id: str,
        actor_id: str,
        verdict: str,
        reason: str,
    ) -> dict[str, Any]:
        await self._session.scalar(
            select(CompanyContextTable)
            .where(CompanyContextTable.company_id == company_id)
            .with_for_update()
        )
        work = await self._session.scalar(
            select(WorkItemTable)
            .where(
                WorkItemTable.company_id == company_id, WorkItemTable.work_item_id == work_item_id
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if work is None:
            raise ExecutionDenied("work_item_not_found", 404)
        artifact = await self._session.get(ArtifactTable, artifact_id)
        if artifact is None or not artifact.run_id:
            raise ExecutionDenied("artifact_not_found", 404)
        run = await self._session.scalar(
            select(AgentRunTable)
            .where(
                AgentRunTable.company_id == company_id, AgentRunTable.work_item_id == work_item_id
            )
            .order_by(AgentRunTable.started_at.desc(), AgentRunTable.run_id.desc())
            .limit(1)
        )
        if run is None:
            raise ExecutionDenied("acceptance_run_required", 400)
        validate_outcome(
            work_item_record(work),
            agent_run_record(run),
            artifact_record(artifact),
            reason=reason,
            verdict=verdict,
        )
        evidence = (artifact.metadata_json or {}).get("evidence")
        if evidence is not None and (
            hash_evidence(evidence) != artifact.content_hash
            or evidence.get("run_id") != run.run_id
            or evidence.get("status") != "succeeded"
        ):
            raise ExecutionDenied("artifact_evidence_integrity_failed", 400)
        self._require_payload_integrity(evidence, run)
        acceptance_id = f"acc_{uuid4().hex}"
        acceptance = OutcomeAcceptanceTable(
            acceptance_id=acceptance_id,
            company_id=company_id,
            work_item_id=work_item_id,
            artifact_id=artifact_id,
            run_id=run.run_id,
            artifact_hash=artifact.content_hash,
            verdict=verdict,
            actor_id=actor_id,
            reason=reason.strip(),
            created_at=datetime.now(UTC),
        )
        self._session.add(acceptance)
        metadata = dict(work.metadata_json or {})
        if verdict == "accepted":
            metadata.update(accepted_artifact_id=artifact_id, acceptance_id=acceptance_id)
        else:
            metadata.pop("accepted_artifact_id", None)
            metadata.pop("acceptance_id", None)
        work.metadata_json = metadata
        await SqlAlchemyControlPlaneAuditEventStore(self._session).append_audit_event(
            AuditEvent(
                company_id=company_id,
                target_type="artifact",
                target_id=artifact_id,
                action=f"outcome.{verdict}",
                actor_type="operator",
                actor_id=actor_id,
                work_item_id=work_item_id,
                run_id=run.run_id,
                detail={
                    "acceptance_id": acceptance_id,
                    "artifact_hash": artifact.content_hash,
                    "reason": reason.strip(),
                },
            )
        )
        await self._session.flush()
        return {
            "work_item": work_item_record(work).model_dump(mode="json"),
            "acceptance": {
                "acceptance_id": acceptance_id,
                "artifact_id": artifact_id,
                "artifact_hash": artifact.content_hash,
                "run_id": run.run_id,
                "verdict": verdict,
                "actor_id": actor_id,
                "reason": reason.strip(),
            },
        }

    async def require_accepted(self, work: WorkItemTable) -> None:
        acceptance = await self._session.get(
            OutcomeAcceptanceTable, (work.metadata_json or {}).get("acceptance_id", "")
        )
        artifact = (
            await self._session.get(ArtifactTable, acceptance.artifact_id) if acceptance else None
        )
        latest_run_id = await self._session.scalar(
            select(AgentRunTable.run_id)
            .where(
                AgentRunTable.company_id == work.company_id,
                AgentRunTable.work_item_id == work.work_item_id,
            )
            .order_by(AgentRunTable.started_at.desc(), AgentRunTable.run_id.desc())
            .limit(1)
        )
        if (
            acceptance is None
            or acceptance.verdict != "accepted"
            or artifact is None
            or acceptance.company_id != work.company_id
            or acceptance.work_item_id != work.work_item_id
            or acceptance.artifact_hash != artifact.content_hash
            or acceptance.run_id != latest_run_id
        ):
            raise ExecutionDenied("accepted_artifact_required", 409)
        run = await self._session.get(AgentRunTable, acceptance.run_id, populate_existing=True)
        if run is None:
            raise ExecutionDenied("accepted_artifact_required", 409)
        evidence = (artifact.metadata_json or {}).get("evidence")
        if evidence is not None and hash_evidence(evidence) != artifact.content_hash:
            raise ExecutionDenied("artifact_evidence_integrity_failed", 409)
        self._require_payload_integrity(evidence, run)

    @staticmethod
    def _require_payload_integrity(evidence: dict[str, Any] | None, run: AgentRunTable) -> None:
        # Historical envelopes lack payload hashes; new run proofs bind the
        # entire stored input/output without duplicating sensitive payloads.
        if evidence is None:
            return
        expected = {
            "input_payload_hash": hash_evidence(run.input_event or {}),
            "output_payload_hash": hash_evidence({"output_events": run.output_events or []}),
        }
        if any(key in evidence and evidence[key] != value for key, value in expected.items()):
            raise ExecutionDenied("artifact_evidence_integrity_failed", 409)
