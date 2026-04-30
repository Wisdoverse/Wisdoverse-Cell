"""Convert Coordinator decisions into EventBus events."""
from shared.schemas.coordinator import CoordinatorResponse
from shared.schemas.event import Event, EventTypes

from .models import Decision


def decision_to_event(decision: Decision) -> Event:
    """Convert a Decision into an Event the target Agent understands."""
    target = decision.target_agent

    if target == "dev-agent":
        return Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="coordinator",
            payload={
                "wp_id": decision.context.get("wp_id"),
                "tasks": decision.context.get("tasks", []),
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    if target == "qa-agent":
        return Event.create(
            event_type=EventTypes.QA_RUN_REQUESTED,
            source_agent="coordinator",
            payload={
                "agent_name": decision.context.get("agent_name"),
                "commit_sha": decision.context.get("commit_sha"),
                "mr_iid": decision.context.get("mr_iid"),
                "gitlab_project_id": decision.context.get("gitlab_project_id"),
                "files_changed": decision.context.get("files_changed", []),
                "requested_by": "coordinator",
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    if target == "chat-agent":
        return Event.create(
            event_type=EventTypes.COORDINATOR_RESPONSE,
            source_agent="coordinator",
            payload=CoordinatorResponse(
                command_id=decision.command_id or "",
                status=decision.status or "completed",
                summary=decision.summary or "",
            ).model_dump(),
        )

    return Event.create(
        event_type=EventTypes.COORDINATOR_DISPATCH,
        source_agent="coordinator",
        payload={
            "target_agent": target,
            "task_id": decision.task_id,
            "instruction": decision.instruction,
            "workflow_id": decision.workflow_id,
            "scratchpad_ref": decision.scratchpad_ref,
        },
    )
