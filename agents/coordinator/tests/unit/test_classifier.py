"""Tests for Coordinator event classifier."""
from shared.schemas.event import Event, EventTypes


def test_classify_coordinator_command():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "create feature",
            "original_message": "新功能",
            "user_id": "u1",
            "user_name": "Alice",
        },
    )
    result = classify_event(event)
    assert result.kind == "command"
    assert result.data.command_id == "cmd_001"


def test_classify_task_notification():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.TASK_NOTIFICATION,
        source_agent="dev-agent",
        payload={
            "task_id": "task_001",
            "agent_id": "dev-agent",
            "status": "completed",
            "summary": "Done",
        },
    )
    result = classify_event(event)
    assert result.kind == "notification"
    assert result.data.status == "completed"


def test_classify_task_progress():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.TASK_PROGRESS,
        source_agent="dev-agent",
        payload={
            "task_id": "task_001",
            "agent_id": "dev-agent",
            "tool_use_count": 5,
            "llm_token_count": 1200,
        },
    )
    result = classify_event(event)
    assert result.kind == "progress"
    assert result.data.tool_use_count == 5


def test_classify_generic_event():
    from agents.coordinator.core.classifier import classify_event
    event = Event.create(
        event_type=EventTypes.PM_DECOMPOSE_COMPLETED,
        source_agent="pjm-agent",
        payload={"wp_id": 100, "tasks": []},
    )
    result = classify_event(event)
    assert result.kind == "event"
    assert result.data.event_type == EventTypes.PM_DECOMPOSE_COMPLETED
