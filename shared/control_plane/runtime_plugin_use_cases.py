"""Application use cases for the control-plane runtime plugin."""
from __future__ import annotations

from typing import Any

from shared.control_plane.context import ControlPlaneRunContext
from shared.schemas.event import Event, EventTypes

from .models import AgentRun, AgentRunStatus, AuditEvent, CompanyContext
from .run_evidence import create_run_evidence_artifact
from .runtime_plugin_ports import ControlPlaneRuntimePluginStore


def _lookup_context_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event_to_dict(event: Event) -> dict[str, Any]:
    return event.model_dump(mode="json")


def _events_to_dict(events: list[Event]) -> list[dict[str, Any]]:
    return [event.model_dump(mode="json") for event in events]


async def start_event_run(
    store: ControlPlaneRuntimePluginStore,
    *,
    agent_id: str,
    event: Event,
    default_company_id: str,
    default_company_name: str,
) -> ControlPlaneRunContext:
    """Create a running AgentRun and its start audit event."""
    company_id = _company_id_from_payload(event.payload, default_company_id)
    await _ensure_company(store, company_id, default_company_name)
    run = await store.create_agent_run(
        AgentRun(
            company_id=company_id,
            agent_id=agent_id,
            status=AgentRunStatus.RUNNING,
            trace_id=event.metadata.trace_id,
            goal_id=_lookup_context_value(event.payload, "goal_id"),
            work_item_id=_lookup_context_value(event.payload, "work_item_id"),
            trigger_event_id=event.event_id,
            input_event=_event_to_dict(event),
        )
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.AGENT_RUN_STARTED,
            target_type="agent_run",
            target_id=run.run_id,
            actor_type="agent",
            actor_id=agent_id,
            trace_id=event.metadata.trace_id,
            run_id=run.run_id,
            work_item_id=run.work_item_id,
            detail={
                "event_id": event.event_id,
                "event_type": event.event_type,
            },
        )
    )
    return ControlPlaneRunContext(
        company_id=company_id,
        run_id=run.run_id,
        agent_id=agent_id,
        trace_id=event.metadata.trace_id,
        goal_id=run.goal_id,
        work_item_id=run.work_item_id,
    )


async def complete_event_run(
    store: ControlPlaneRuntimePluginStore,
    *,
    run_id: str,
    agent_id: str,
    event: Event,
    output_events: list[Event],
) -> bool:
    """Mark a runtime event run succeeded and create evidence."""
    output_payloads = _events_to_dict(output_events)
    run = await store.update_agent_run_status(
        run_id,
        AgentRunStatus.SUCCEEDED,
        output_events=output_payloads,
    )
    if run is None:
        return False

    await store.append_audit_event(
        AuditEvent(
            company_id=run.company_id,
            action=EventTypes.AGENT_RUN_SUCCEEDED,
            target_type="agent_run",
            target_id=run_id,
            actor_type="agent",
            actor_id=agent_id,
            trace_id=event.metadata.trace_id,
            run_id=run_id,
            work_item_id=run.work_item_id,
            detail={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "output_event_count": len(output_events),
            },
        )
    )
    await create_run_evidence_artifact(
        store,
        company_id=run.company_id,
        agent_id=agent_id,
        run_id=run_id,
        actor_type="agent",
        actor_id=agent_id,
        trigger=event.event_type,
        trace_id=event.metadata.trace_id,
        goal_id=run.goal_id,
        work_item_id=run.work_item_id,
        adapter_type="agent_runtime",
        status="succeeded",
        input_event=_event_to_dict(event),
        output_events=output_payloads,
        output_summary=f"{len(output_events)} output event(s)",
        generated_by="control_plane_runtime_plugin",
    )
    return True


async def fail_event_run(
    store: ControlPlaneRuntimePluginStore,
    *,
    run_id: str,
    agent_id: str,
    event: Event,
    error: BaseException,
    default_company_id: str,
) -> bool:
    """Mark a runtime event run failed and create evidence."""
    failure_event = Event.create(
        event_type=EventTypes.AGENT_RUN_FAILED,
        source_agent=agent_id,
        payload={
            "company_id": _company_id_from_payload(event.payload, default_company_id),
            "run_id": run_id,
            "status": "failed",
            "error_category": type(error).__name__,
            "error_message": str(error),
        },
        trace_id=event.metadata.trace_id,
    )
    output_events = [_event_to_dict(failure_event)]
    run = await store.update_agent_run_status(
        run_id,
        AgentRunStatus.FAILED,
        error_category=type(error).__name__,
        error_message=str(error),
        last_successful_step="handler_started",
        output_events=output_events,
    )
    if run is None:
        return False

    await store.append_audit_event(
        AuditEvent(
            company_id=run.company_id,
            action=EventTypes.AGENT_RUN_FAILED,
            target_type="agent_run",
            target_id=run_id,
            actor_type="agent",
            actor_id=agent_id,
            trace_id=event.metadata.trace_id,
            run_id=run_id,
            work_item_id=run.work_item_id,
            detail={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
    )
    await create_run_evidence_artifact(
        store,
        company_id=run.company_id,
        agent_id=agent_id,
        run_id=run_id,
        actor_type="agent",
        actor_id=agent_id,
        trigger=event.event_type,
        trace_id=event.metadata.trace_id,
        goal_id=run.goal_id,
        work_item_id=run.work_item_id,
        adapter_type="agent_runtime",
        status="failed",
        input_event=_event_to_dict(event),
        output_events=output_events,
        output_summary=None,
        error_category=type(error).__name__,
        error_message=str(error),
        generated_by="control_plane_runtime_plugin",
    )
    return True


async def bootstrap_core_agent_roles(
    store: ControlPlaneRuntimePluginStore,
    *,
    company_id: str,
    company_name: str,
) -> list[str]:
    """Ensure all core control-plane agent roles exist."""
    created_role_agents = await store.ensure_core_organization_role_agents(
        company_id=company_id,
        company_name=company_name,
    )
    created_runtime_agents = await store.ensure_core_runtime_agent_roles(
        company_id=company_id,
        company_name=company_name,
    )
    return created_role_agents + created_runtime_agents


async def _ensure_company(
    store: ControlPlaneRuntimePluginStore,
    company_id: str,
    company_name: str,
) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name=company_name,
        )
    )


def _company_id_from_payload(payload: dict[str, Any], default_company_id: str) -> str:
    return _lookup_context_value(payload, "company_id") or default_company_id
