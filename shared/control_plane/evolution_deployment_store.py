"""Release preparation and durable acknowledgement in local transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.evolution.release_contract import SkillReleaseCommand, canonical_hash

from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .domain.evolution_deployment import TARGET_STATES, validate_release
from .domain.evolution_proposal import EvolutionProposal as EvolutionProposalAggregate
from .domain.execution_policy import ExecutionDenied
from .domain_event_audit import DomainEventAuditContext, append_control_plane_domain_event_audits
from .domain_records import evolution_proposal_record
from .evolution_deployment_models import EvolutionDeploymentTable
from .evolution_evaluation_models import EvolutionEvaluationReportTable
from .models import ApprovalCategory, ApprovalRequest, AuditEvent
from .tables import ApprovalRequestTable, EvolutionProposalTable


def _as_utc(value: datetime) -> datetime:
    """Normalize DB datetimes that may be naive under SQLite fixtures."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlAlchemyEvolutionDeploymentStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def checkpoint(self) -> None:
        await self._session.commit()

    async def pending(self, *, company_id: str, proposal_id: str) -> SkillReleaseCommand:
        row = await self._session.scalar(
            select(EvolutionDeploymentTable).where(
                EvolutionDeploymentTable.company_id == company_id,
                EvolutionDeploymentTable.proposal_id == proposal_id,
            )
        )
        if row is None or row.state != "pending":
            raise ExecutionDenied("pending_release_not_found", 404)
        return SkillReleaseCommand.model_validate(row.command)

    async def recover_expired_pending(
        self, command: SkillReleaseCommand, *, actor_id: str
    ) -> SkillReleaseCommand:
        """Replace an expired command after the receiver definitively returned 404.

        The caller performs receiver lookup before entering this method.
        Proposal then deployment row locks serialize recovery; command ID and
        payload hash provide the ownership CAS. The prior immutable command is
        retained in the audit event before the pending row is reset.
        """
        proposal = await self._session.scalar(
            select(EvolutionProposalTable)
            .where(
                EvolutionProposalTable.company_id == command.company_id,
                EvolutionProposalTable.proposal_id == command.proposal_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = await self._session.scalar(
            select(EvolutionDeploymentTable)
            .where(
                EvolutionDeploymentTable.company_id == command.company_id,
                EvolutionDeploymentTable.proposal_id == command.proposal_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if proposal is None or row is None:
            raise ExecutionDenied("pending_release_not_found", 404)
        stored = SkillReleaseCommand.model_validate(row.command)
        if (
            row.state != "pending"
            or stored.command_id != command.command_id
            or canonical_hash(stored.model_dump(mode="json"))
            != canonical_hash(command.model_dump(mode="json"))
        ):
            raise ExecutionDenied("evolution_release_owner_lost", 409)
        now = datetime.now(UTC)
        if _as_utc(stored.expires_at) > now:
            raise ExecutionDenied("release_command_not_expired", 409)

        last_state = (row.acknowledgement or {}).get("state")
        await self._audit(
            command.company_id,
            command.proposal_id,
            "evolution.release_expired_command_recovered",
            actor_id,
            {
                "deployment_id": row.deployment_id,
                "superseded_command": stored.model_dump(mode="json"),
                "superseded_payload_hash": canonical_hash(stored.model_dump(mode="json")),
                "receiver_lookup": "not_found",
                "restored_acknowledged_state": last_state,
            },
        )
        deployment_id_override = row.deployment_id
        if last_state is None:
            if stored.action != "shadow" or row.acknowledgement:
                raise ExecutionDenied("release_acknowledged_state_missing", 409)
            await self._session.delete(row)
            await self._session.flush()
        elif last_state in {"shadow", "canary", "active"}:
            row.state = last_state
            row.updated_at = now
            await self._session.flush()
        else:
            raise ExecutionDenied("release_acknowledged_state_invalid", 409)

        return await self.prepare(
            company_id=stored.company_id,
            proposal_id=stored.proposal_id,
            evaluation_report_id=stored.evaluation_report_id,
            skill_id=stored.skill_id,
            agent_id=stored.agent_id,
            baseline_version=stored.baseline_version,
            candidate_version=stored.candidate_version,
            baseline_config_hash=stored.baseline_config_hash,
            candidate_config_hash=stored.candidate_config_hash,
            action=stored.action,
            actor_id=actor_id,
            deployment_id_override=deployment_id_override,
        )

    async def prepare(
        self,
        *,
        company_id: str,
        proposal_id: str,
        evaluation_report_id: str,
        skill_id: str,
        agent_id: str,
        baseline_version: int,
        candidate_version: int,
        baseline_config_hash: str,
        candidate_config_hash: str,
        action: str,
        actor_id: str,
        deployment_id_override: str | None = None,
    ) -> SkillReleaseCommand:
        now = datetime.now(UTC)
        proposal = await self._session.scalar(
            select(EvolutionProposalTable)
            .where(
                EvolutionProposalTable.company_id == company_id,
                EvolutionProposalTable.proposal_id == proposal_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        report = await self._session.get(EvolutionEvaluationReportTable, evaluation_report_id)
        if (
            proposal is None
            or report is None
            or report.company_id != company_id
            or report.proposal_id != proposal_id
        ):
            raise ExecutionDenied("evolution_evidence_not_found", 404)
        existing = await self._session.scalar(
            select(EvolutionDeploymentTable)
            .where(EvolutionDeploymentTable.proposal_id == proposal_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        snapshot = dict(
            company_id=company_id,
            proposal_id=proposal_id,
            evaluation_report_id=evaluation_report_id,
            evaluation_hash=canonical_hash(report.comparison_report),
            skill_id=skill_id,
            agent_id=agent_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            baseline_config_hash=baseline_config_hash,
            candidate_config_hash=candidate_config_hash,
        )
        if existing:
            old = SkillReleaseCommand.model_validate(existing.command)
            if any(getattr(old, key) != value for key, value in snapshot.items()):
                raise ExecutionDenied("frozen_release_configuration_changed")
            if existing.desired_action == action and existing.state == "pending":
                if _as_utc(old.expires_at) <= now:
                    raise ExecutionDenied("release_command_expired_recovery_required", 409)
                if old.approval_id:
                    approval = await self._session.scalar(
                        select(ApprovalRequestTable)
                        .where(ApprovalRequestTable.approval_id == old.approval_id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    if (
                        approval is None
                        or approval.status != "approved"
                        or not approval.expires_at
                        or _as_utc(approval.expires_at) <= now
                    ):
                        raise ExecutionDenied("skill_release_approval_revoked", 403)
                return old
        validate_release(
            tier=proposal.tier,
            state=existing.state if existing else None,
            action=action,
            report=report.comparison_report,
            baseline_ref=f"{skill_id}@{baseline_version}",
            candidate_ref=f"{skill_id}@{candidate_version}",
        )
        deployment_id = (
            existing.deployment_id if existing else (deployment_id_override or f"dep_{uuid4().hex}")
        )
        decision_hash = canonical_hash(
            {**snapshot, "deployment_id": deployment_id, "action": action}
        )
        approval_id = None
        if action != "shadow":
            approvals = (
                await self._session.scalars(
                    select(ApprovalRequestTable)
                    .where(
                        ApprovalRequestTable.company_id == company_id,
                        ApprovalRequestTable.metadata_json["release_decision_hash"].as_string()
                        == decision_hash,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
            valid = [a for a in approvals if a.expires_at and _as_utc(a.expires_at) > now]
            granted = next((a for a in valid if a.status == "approved"), None)
            if granted is None:
                if not any(a.status == "pending" for a in valid):
                    await SqlAlchemyControlPlaneApprovalStore(self._session).request_approval(
                        ApprovalRequest(
                            company_id=company_id,
                            category=ApprovalCategory.TECHNICAL,
                            requested_by=actor_id,
                            source_agent_id=agent_id,
                            proposed_action=f"{action} L1 skill {skill_id}@{candidate_version}",
                            reason="Review frozen comparative quality, full attempt cost and interventions.",
                            risk="Live routing can affect real work and consume budget.",
                            rollback_note=f"Restore frozen baseline {skill_id}@{baseline_version} after CAS verification.",
                            affected_resources=[f"skill:{skill_id}", f"proposal:{proposal_id}"],
                            expires_at=now + timedelta(hours=24),
                            metadata={
                                "release_decision_hash": decision_hash,
                                "release_snapshot": snapshot,
                                "action": action,
                            },
                        )
                    )
                await self.checkpoint()
                raise ExecutionDenied("skill_release_approval_required", 403)
            approval_id = granted.approval_id
        command = SkillReleaseCommand.model_validate(
            {
                **snapshot,
                "command_id": f"cmd_{uuid4().hex}",
                "deployment_id": deployment_id,
                "action": action,
                "approval_id": approval_id,
                "expires_at": now + timedelta(hours=1),
            }
        )
        if existing is None:
            existing = EvolutionDeploymentTable(
                deployment_id=deployment_id,
                company_id=company_id,
                proposal_id=proposal_id,
                evaluation_report_id=evaluation_report_id,
                acknowledgement={},
            )
            self._session.add(existing)
        existing.state = "pending"
        existing.desired_action = action
        existing.command = command.model_dump(mode="json")
        existing.updated_at = now
        await self._audit(
            company_id,
            proposal_id,
            "evolution.release_requested",
            actor_id,
            {
                "deployment_id": deployment_id,
                "command_id": command.command_id,
                "action": action,
                "evaluation_report_id": evaluation_report_id,
                "approval_id": approval_id,
            },
        )
        await self._session.flush()
        return command

    async def acknowledge(
        self, command: SkillReleaseCommand, response: dict[str, Any], *, actor_id: str
    ) -> None:
        expected = TARGET_STATES[command.action]
        if (
            response.get("state") != expected
            or response.get("deployment_id") != command.deployment_id
        ):
            raise ExecutionDenied("evolution_receiver_state_mismatch", 502)
        proposal = await self._session.scalar(
            select(EvolutionProposalTable)
            .where(
                EvolutionProposalTable.company_id == command.company_id,
                EvolutionProposalTable.proposal_id == command.proposal_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        deployment = await self._session.scalar(
            select(EvolutionDeploymentTable)
            .where(
                EvolutionDeploymentTable.company_id == command.company_id,
                EvolutionDeploymentTable.proposal_id == command.proposal_id,
                EvolutionDeploymentTable.deployment_id == command.deployment_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if proposal is None or deployment is None or deployment.state != "pending":
            raise ExecutionDenied("evolution_release_owner_lost", 409)
        stored = SkillReleaseCommand.model_validate(deployment.command)
        if stored.command_id != command.command_id or canonical_hash(
            stored.model_dump(mode="json")
        ) != canonical_hash(command.model_dump(mode="json")):
            raise ExecutionDenied("evolution_release_owner_lost", 409)
        deployment.state = expected
        deployment.acknowledgement = response
        deployment.updated_at = datetime.now(UTC)
        if proposal.rollout_state != expected:
            aggregate = EvolutionProposalAggregate.from_record(evolution_proposal_record(proposal))
            aggregate.advance_rollout(expected)
            proposal.rollout_state = aggregate.rollout_state.value
            await append_control_plane_domain_event_audits(
                SqlAlchemyControlPlaneAuditEventStore(self._session),
                aggregate.pull_events(),
                DomainEventAuditContext(actor_type="operator", actor_id=actor_id),
            )
        proposal.metadata_json = {
            **(proposal.metadata_json or {}),
            "deployment_id": command.deployment_id,
            "evaluation_report_id": command.evaluation_report_id,
            "experiment_id": response.get("experiment_id"),
            "deployed_skill_version": command.candidate_version
            if expected == "active"
            else command.baseline_version,
        }
        await self._audit(
            command.company_id, command.proposal_id, "evolution.release_applied", actor_id, response
        )

    async def _audit(
        self, company_id: str, proposal_id: str, action: str, actor_id: str, detail: dict[str, Any]
    ) -> None:
        await SqlAlchemyControlPlaneAuditEventStore(self._session).append_audit_event(
            AuditEvent(
                company_id=company_id,
                target_type="evolution_proposal",
                target_id=proposal_id,
                action=action,
                actor_type="operator",
                actor_id=actor_id,
                detail=detail,
            )
        )
