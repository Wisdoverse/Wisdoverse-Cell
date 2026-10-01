"""Application helpers for control-plane agent-run lifecycle records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.core.ids import IDPrefix, generate_id
from shared.schemas.event import EventTypes

from ...agent_operation_ports import ControlPlaneAgentOperationStore
from ...domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
from ...models import AgentRun, AgentRunStatus, AuditEvent
from ...run_evidence import create_run_evidence_artifact
from ..agent_run import (
    AgentRun as AgentRunAggregate,
)
from ..agent_run import (
    AgentRunStatusChanged,
)


async def _validate_run_transition_via_aggregate(
    store: ControlPlaneAgentOperationStore,
    run_id: str,
    target_status: AgentRunStatus,
) -> list[AgentRunStatusChanged]:
    """Load the run, transition via the AgentRun aggregate, return raised events.

    Closes the DDD-001 seed → implementation gap by routing every
    AgentRun status mutation through the aggregate's FSM
    (``VALID_TRANSITIONS``). If a caller attempts an illegal transition
    (for example, COMPLETED → COMPLETED, or FAILED → SUCCEEDED), the
    aggregate raises ``InvalidAgentRunTransitionError`` before the
    persistence write touches the database.

    Returns the in-memory ``AgentRunStatusChanged`` events for the
    caller to forward to the outbox in the same transaction (Stage 2
    aggregate-raised events pattern per
    ``architecture-principles.md`` §4.8).
    """
    current = await store.get_agent_run(run_id)
    if current is None:
        # No row yet — the start path constructs the run already at
        # RUNNING, so a missing row here means the caller is mid-init.
        # Skip FSM validation; the persistence layer will surface the
        # error if the row truly never lands.
        return []
    aggregate = AgentRunAggregate.from_record(current)
    aggregate.transition_to(target_status)
    return aggregate.pull_events()


__all_extra__ = (
    "AgentRunAggregate",
    "AgentRunStatusChanged",
    "InvalidAgentRunTransitionError",
)


@dataclass(frozen=True, slots=True)
class AgentWakeupRunRecord:
    """Persisted wakeup run and its synthetic input event."""

    run: Any
    input_event: dict[str, Any]


async def start_agent_wakeup_run(
    store: ControlPlaneAgentOperationStore,
    agent: Any,
    *,
    input_payload: dict[str, Any] | None,
    actor_id: str,
    trace_id: str | None,
    goal_id: str | None,
    work_item_id: str | None,
    trigger: str,
    run_id: str | None = None,
) -> AgentWakeupRunRecord:
    """Create a running wakeup AgentRun and its start audit event."""
    trigger_event_id = generate_id(IDPrefix.EVENT)
    run_model = AgentRun(
        company_id=agent.company_id,
        agent_id=agent.agent_id,
        status=AgentRunStatus.RUNNING,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        trigger_event_id=trigger_event_id,
    )
    if run_id is not None:
        run_model.run_id = run_id
    input_event = {
        "event_id": trigger_event_id,
        "event_type": EventTypes.AGENT_WAKEUP_REQUESTED,
        "source_agent": actor_id,
        "payload": {
            "company_id": agent.company_id,
            "agent_id": agent.agent_id,
            "run_id": run_model.run_id,
            "actor_id": actor_id,
            "input": input_payload or {},
            "trace_id": trace_id,
            "goal_id": goal_id,
            "work_item_id": work_item_id,
        },
        "metadata": {"trace_id": trace_id},
    }
    run_model.input_event = input_event
    run = await store.create_agent_run(run_model)
    await append_agent_run_audit(
        store,
        action=EventTypes.AGENT_RUN_STARTED,
        run_id=run.run_id,
        company_id=agent.company_id,
        agent_id=agent.agent_id,
        actor_id=actor_id,
        trace_id=trace_id,
        work_item_id=work_item_id,
        detail={
            "trigger": trigger,
            "adapter_type": agent.adapter_type,
        },
    )
    return AgentWakeupRunRecord(run=run, input_event=input_event)


async def complete_agent_wakeup_run(
    store: ControlPlaneAgentOperationStore,
    agent: Any,
    *,
    run_id: str,
    input_event: dict[str, Any],
    output: dict[str, Any],
    actor_id: str,
    trace_id: str | None,
    goal_id: str | None,
    work_item_id: str | None,
    trigger: str,
) -> str:
    """Mark a wakeup run succeeded and create evidence."""
    completion_event = build_agent_wakeup_completion_event(
        agent=agent,
        run_id=run_id,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        status="succeeded",
        output=output,
    )
    # Route through the AgentRun aggregate to enforce the FSM before
    # the persistence write (DDD-001 implementation).
    domain_events = await _validate_run_transition_via_aggregate(
        store, run_id, AgentRunStatus.SUCCEEDED
    )
    await store.update_agent_run_status(
        run_id,
        AgentRunStatus.SUCCEEDED,
        output_events=[completion_event],
    )
    detail = {
        "trigger": trigger,
        "adapter_type": agent.adapter_type,
        "output_summary": output.get("summary") or output.get("status"),
    }
    if domain_events:
        await append_control_plane_domain_event_audits(
            store,
            domain_events,
            DomainEventAuditContext(
                actor_type="user",
                actor_id=actor_id,
                trace_id=trace_id,
                run_id=run_id,
                work_item_id=work_item_id,
                detail=detail,
            ),
        )
    else:
        await append_agent_run_audit(
            store,
            action=EventTypes.AGENT_RUN_SUCCEEDED,
            run_id=run_id,
            company_id=agent.company_id,
            agent_id=agent.agent_id,
            actor_id=actor_id,
            trace_id=trace_id,
            work_item_id=work_item_id,
            detail=detail,
        )
    artifact = await create_run_evidence_artifact(
        store,
        company_id=agent.company_id,
        agent_id=agent.agent_id,
        run_id=run_id,
        actor_type="user",
        actor_id=actor_id,
        trigger=trigger,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        adapter_type=str(agent.adapter_type or "builtin"),
        status="succeeded",
        input_event=input_event,
        output_events=[completion_event],
        output_summary=output.get("summary") or output.get("status"),
        generated_by="control_plane_agent_runner",
    )
    return artifact.artifact_id


async def fail_agent_wakeup_run(
    store: ControlPlaneAgentOperationStore,
    agent: Any,
    *,
    run_id: str,
    input_event: dict[str, Any],
    actor_id: str,
    trace_id: str | None,
    goal_id: str | None,
    work_item_id: str | None,
    trigger: str,
    error_category: str,
    error_message: str,
    cancelled: bool = False,
) -> None:
    """Mark a wakeup run failed and create evidence."""
    completion_event = build_agent_wakeup_completion_event(
        agent=agent,
        run_id=run_id,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        status="cancelled" if cancelled else "failed",
        output={},
        error_category=error_category,
        error_message=error_message,
    )
    # Route through the AgentRun aggregate to enforce the FSM before
    # the persistence write (DDD-001 implementation).
    domain_events = await _validate_run_transition_via_aggregate(
        store, run_id, AgentRunStatus.CANCELLED if cancelled else AgentRunStatus.FAILED
    )
    await store.update_agent_run_status(
        run_id,
        AgentRunStatus.CANCELLED if cancelled else AgentRunStatus.FAILED,
        error_category=error_category,
        error_message=error_message,
        last_successful_step="agent_definition_loaded",
        output_events=[completion_event],
    )
    detail = {
        "trigger": trigger,
        "adapter_type": agent.adapter_type,
        "error_category": error_category,
        "error": error_message,
    }
    if domain_events:
        await append_control_plane_domain_event_audits(
            store,
            domain_events,
            DomainEventAuditContext(
                actor_type="user",
                actor_id=actor_id,
                trace_id=trace_id,
                run_id=run_id,
                work_item_id=work_item_id,
                detail=detail,
            ),
        )
    else:
        await append_agent_run_audit(
            store,
            action=EventTypes.AGENT_RUN_FAILED,
            run_id=run_id,
            company_id=agent.company_id,
            agent_id=agent.agent_id,
            actor_id=actor_id,
            trace_id=trace_id,
            work_item_id=work_item_id,
            detail=detail,
        )
    await create_run_evidence_artifact(
        store,
        company_id=agent.company_id,
        agent_id=agent.agent_id,
        run_id=run_id,
        actor_type="user",
        actor_id=actor_id,
        trigger=trigger,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        adapter_type=str(agent.adapter_type or "builtin"),
        status="cancelled" if cancelled else "failed",
        input_event=input_event,
        output_events=[completion_event],
        output_summary=None,
        error_category=error_category,
        error_message=error_message,
        generated_by="control_plane_agent_runner",
    )


def build_agent_wakeup_completion_event(
    *,
    agent: Any,
    run_id: str,
    trace_id: str | None,
    goal_id: str | None,
    work_item_id: str | None,
    status: str,
    output: dict[str, Any],
    error_category: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build the synthetic wakeup completion event persisted on AgentRun."""
    payload = {
        "company_id": agent.company_id,
        "agent_id": agent.agent_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "goal_id": goal_id,
        "work_item_id": work_item_id,
        "status": status,
        "output": output,
    }
    if error_category:
        payload["error_category"] = error_category
    if error_message:
        payload["error_message"] = error_message
    return {
        "event_type": EventTypes.AGENT_WAKEUP_COMPLETED,
        "source_agent": agent.agent_id,
        "payload": payload,
        "metadata": {"trace_id": trace_id},
        "event_id": generate_id(IDPrefix.EVENT),
    }


async def append_agent_run_audit(
    store: ControlPlaneAgentOperationStore,
    *,
    action: str,
    run_id: str,
    company_id: str,
    agent_id: str,
    actor_id: str,
    trace_id: str | None,
    work_item_id: str | None,
    detail: dict[str, Any],
) -> None:
    """Append an audit event for one agent run."""
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=action,
            target_type="agent_run",
            target_id=run_id,
            actor_type="user",
            actor_id=actor_id,
            trace_id=trace_id,
            run_id=run_id,
            work_item_id=work_item_id,
            detail=detail,
        )
    )


__all__ = [
    "AgentWakeupRunRecord",
    "append_agent_run_audit",
    "build_agent_wakeup_completion_event",
    "complete_agent_wakeup_run",
    "fail_agent_wakeup_run",
    "start_agent_wakeup_run",
]
