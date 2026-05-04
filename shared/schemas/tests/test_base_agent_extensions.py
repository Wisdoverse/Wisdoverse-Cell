"""Tests for BaseAgent extension methods (progress, notification, scratchpad)."""
import pytest

from shared.schemas.event import EventTypes


class _TestAgent:
    """Minimal concrete agent for testing BaseAgent helpers."""

    @staticmethod
    def _make(agent_id: str = "test-agent"):
        from shared.schemas.agent import BaseAgent

        class ConcreteAgent(BaseAgent):
            async def handle_event(self, event):
                return []
            async def handle_request(self, request):
                return {}

        return ConcreteAgent(
            agent_id=agent_id,
            agent_name="Test Agent",
        )


def test_base_agent_rejects_invalid_runtime_agent_id():
    for agent_id in ("", "   ", "Test Agent", "test.agent"):
        with pytest.raises(ValueError, match="agent_id must be"):
            _TestAgent._make(agent_id=agent_id)


def test_create_task_notification():
    agent = _TestAgent._make()
    event = agent._create_task_notification(
        task_id="task_001",
        status="completed",
        summary="Task finished",
    )
    assert event.event_type == EventTypes.TASK_NOTIFICATION
    assert event.source_agent == "test-agent"
    assert event.payload["task_id"] == "task_001"
    assert event.payload["agent_id"] == "test-agent"
    assert event.payload["status"] == "completed"
    assert event.payload["summary"] == "Task finished"


def test_create_task_notification_with_result():
    agent = _TestAgent._make()
    event = agent._create_task_notification(
        task_id="task_002",
        status="completed",
        summary="PRD ready",
        result={"prd_id": "prd_001"},
    )
    assert event.payload["result"] == {"prd_id": "prd_001"}


def test_create_task_notification_with_error():
    agent = _TestAgent._make()
    event = agent._create_task_notification(
        task_id="task_003",
        status="failed",
        summary="Build failed",
        error="Compilation error in main.py",
    )
    assert event.payload["status"] == "failed"
    assert event.payload["error"] == "Compilation error in main.py"


def test_create_progress_event():
    agent = _TestAgent._make()
    event = agent._create_progress_event(
        task_id="task_001",
        tool_use_count=5,
        llm_token_count=1200,
    )
    assert event.event_type == EventTypes.TASK_PROGRESS
    assert event.source_agent == "test-agent"
    assert event.payload["task_id"] == "task_001"
    assert event.payload["agent_id"] == "test-agent"
    assert event.payload["tool_use_count"] == 5
    assert event.payload["llm_token_count"] == 1200


def test_create_progress_event_with_activity():
    agent = _TestAgent._make()
    event = agent._create_progress_event(
        task_id="task_001",
        tool_use_count=3,
        llm_token_count=800,
        last_activity={"tool_name": "llm_call", "description": "Analyzing code"},
    )
    assert event.payload["last_activity"]["tool_name"] == "llm_call"
