"""Application helpers for control-plane agent-run lifecycle records."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.core.ids import IDPrefix, generate_id
from shared.schemas.event import EventTypes

from .agent_operation_ports import ControlPlaneAgentOperationStore
from .models import AgentRun, AgentRunStatus, AuditEvent
from .run_evidence import create_run_evidence_artifact


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
    await store.update_agent_run_status(
        run_id,
        AgentRunStatus.SUCCEEDED,
        output_events=[completion_event],
    )
    await append_agent_run_audit(
        store,
        action=EventTypes.AGENT_RUN_SUCCEEDED,
        run_id=run_id,
        company_id=agent.company_id,
        agent_id=agent.agent_id,
        actor_id=actor_id,
        trace_id=trace_id,
        work_item_id=work_item_id,
        detail={
            "trigger": trigger,
            "adapter_type": agent.adapter_type,
            "output_summary": output.get("summary") or output.get("status"),
        },
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
) -> None:
    """Mark a wakeup run failed and create evidence."""
    completion_event = build_agent_wakeup_completion_event(
        agent=agent,
        run_id=run_id,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        status="failed",
        output={},
        error_category=error_category,
        error_message=error_message,
    )
    await store.update_agent_run_status(
        run_id,
        AgentRunStatus.FAILED,
        error_category=error_category,
        error_message=error_message,
        last_successful_step="agent_definition_loaded",
        output_events=[completion_event],
    )
    await append_agent_run_audit(
        store,
        action=EventTypes.AGENT_RUN_FAILED,
        run_id=run_id,
        company_id=agent.company_id,
        agent_id=agent.agent_id,
        actor_id=actor_id,
        trace_id=trace_id,
        work_item_id=work_item_id,
        detail={
            "trigger": trigger,
            "adapter_type": agent.adapter_type,
            "error_category": error_category,
            "error": error_message,
        },
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
        status="failed",
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
