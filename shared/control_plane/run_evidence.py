"""Create verifiable proof artifacts for control-plane agent runs."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from shared.control_plane.models import Artifact, ArtifactType, AuditEvent
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes


def canonical_evidence_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def hash_evidence(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_evidence_json(value).encode("utf-8")).hexdigest()


async def create_run_evidence_artifact(
    repo: ControlPlaneRepository,
    *,
    company_id: str,
    agent_id: str,
    run_id: str,
    actor_type: str,
    actor_id: str,
    trigger: str,
    trace_id: str | None,
    goal_id: str | None,
    work_item_id: str | None,
    adapter_type: str,
    status: str,
    input_event: dict[str, Any] | None,
    output_events: list[dict[str, Any]],
    output_summary: str | None = None,
    error_category: str | None = None,
    error_message: str | None = None,
    generated_by: str = "control_plane",
) -> Any:
    approvals = await repo.list_approvals(
        company_id=company_id,
        run_id=run_id,
        limit=100,
    )
    budget_usage = await repo.list_budget_usage(
        company_id=company_id,
        run_id=run_id,
        limit=100,
    )
    audit_events = await repo.list_audit_events(
        company_id=company_id,
        run_id=run_id,
        limit=100,
    )
    evidence = {
        "schema_version": "1.0",
        "run_id": run_id,
        "company_id": company_id,
        "agent_id": agent_id,
        "status": status,
        "trigger": trigger,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "trace_id": trace_id,
        "goal_id": goal_id,
        "work_item_id": work_item_id,
        "adapter_type": adapter_type,
        "events": {
            "input_event_id": (input_event or {}).get("event_id"),
            "input_event_type": (input_event or {}).get("event_type"),
            "output_event_ids": [
                event.get("event_id") for event in output_events if event.get("event_id")
            ],
            "output_event_types": [
                event.get("event_type")
                for event in output_events
                if event.get("event_type")
            ],
        },
        "approvals": [row.approval_id for row in approvals],
        "budget_usage": [row.usage_id for row in budget_usage],
        "audit_events": [row.audit_event_id for row in audit_events],
        "output_summary": output_summary,
        "error_category": error_category,
        "error_message": error_message,
    }
    content_hash = hash_evidence(evidence)
    artifact = await repo.create_artifact(
        Artifact(
            company_id=company_id,
            artifact_type=ArtifactType.RUN_WALKTHROUGH,
            title=f"Run evidence for {agent_id}",
            uri=f"artifact://control-plane/runs/{run_id}/evidence",
            content_hash=content_hash,
            run_id=run_id,
            work_item_id=work_item_id,
            goal_id=goal_id,
            created_by_agent_id=agent_id,
            metadata={
                "evidence": evidence,
                "hash_algorithm": "sha256",
                "generated_by": generated_by,
            },
        )
    )
    await repo.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.ARTIFACT_CREATED,
            target_type="artifact",
            target_id=artifact.artifact_id,
            actor_type=actor_type,
            actor_id=actor_id,
            trace_id=trace_id,
            run_id=run_id,
            work_item_id=work_item_id,
            detail={
                "artifact_id": artifact.artifact_id,
                "artifact_type": ArtifactType.RUN_WALKTHROUGH.value,
                "uri": artifact.uri,
                "content_hash": content_hash,
                "evidence_for": "agent_run",
            },
        )
    )
    return artifact
