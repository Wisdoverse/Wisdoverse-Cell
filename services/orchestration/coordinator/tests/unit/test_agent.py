# services/orchestration/coordinator/tests/unit/test_agent.py
"""Tests for CoordinatorAgent event handling."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_coordinator_agent_init():
    from services.orchestration.coordinator.service.agent import CoordinatorAgent
    agent = CoordinatorAgent()
    assert agent.agent_id == "coordinator"
    assert EventTypes.COORDINATOR_COMMAND in agent.subscribed_events
    assert EventTypes.TASK_NOTIFICATION in agent.subscribed_events
    assert EventTypes.TASK_PROGRESS in agent.subscribed_events
    assert EventTypes.COORDINATOR_RESPONSE in agent.published_events
    assert EventTypes.COORDINATOR_DISPATCH in agent.published_events
    assert EventTypes.PM_TASKS_READY_FOR_DEV in agent.published_events
    assert EventTypes.QA_RUN_REQUESTED in agent.published_events


@pytest.mark.asyncio
async def test_health_check_reports_initialized_runtime_dependencies(tmp_path):
    from services.orchestration.coordinator.service.agent import CoordinatorAgent
    from shared.infra.scratchpad import Scratchpad

    agent = CoordinatorAgent()
    agent._scratchpad = Scratchpad(str(tmp_path / "scratchpad"))

    before = await agent.health_check()
    await agent._scratchpad.initialize()
    after = await agent.health_check()

    assert before["scratchpad"] is False
    assert after == {
        "scratchpad": True,
        "state_store": True,
        "llm_gateway": True,
    }


@pytest.mark.asyncio
async def test_handle_event_with_command_returns_events():
    from services.orchestration.coordinator.core.models import Decision
    from services.orchestration.coordinator.service.agent import CoordinatorAgent
    agent = CoordinatorAgent()

    mock_decision = Decision(
        target_agent="requirement-manager",
        action="dispatch_task",
        task_id="task_001",
        instruction="Produce PRD",
        workflow_id="wf_001",
    )
    agent._think = AsyncMock(return_value=[mock_decision])
    agent._scratchpad = MagicMock()
    agent._scratchpad.read_incremental = AsyncMock(return_value="")
    agent._scratchpad.update = AsyncMock()
    agent._scratchpad.should_compact = MagicMock(return_value=False)
    agent._state_store = MagicMock()
    agent._state_store.get_agent_states = AsyncMock(return_value={})
    agent._state_store.get_pending_decisions = AsyncMock(return_value=[])
    agent._state_store.persist = AsyncMock()

    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "new feature",
            "original_message": "新功能",
            "user_id": "u1",
            "user_name": "Alice",
        },
    )
    result_events = await agent.handle_event(event)
    assert len(result_events) == 1
    assert result_events[0].event_type == EventTypes.COORDINATOR_DISPATCH
    assert result_events[0].payload["target_agent"] == "requirement-manager"


@pytest.mark.asyncio
async def test_handle_event_with_progress_updates_state():
    from services.orchestration.coordinator.service.agent import CoordinatorAgent
    agent = CoordinatorAgent()

    agent._think = AsyncMock(return_value=[])
    agent._scratchpad = MagicMock()
    agent._scratchpad.read_incremental = AsyncMock(return_value="")
    agent._scratchpad.update = AsyncMock()
    agent._scratchpad.should_compact = MagicMock(return_value=False)
    agent._state_store = MagicMock()
    agent._state_store.get_agent_states = AsyncMock(return_value={})
    agent._state_store.get_pending_decisions = AsyncMock(return_value=[])
    agent._state_store.persist = AsyncMock()
    agent._state_store.update_agent_state = AsyncMock()

    event = Event.create(
        event_type=EventTypes.TASK_PROGRESS,
        source_agent="dev-agent",
        payload={
            "task_id": "task_001",
            "agent_id": "dev-agent",
            "tool_use_count": 3,
            "llm_token_count": 500,
        },
    )
    result_events = await agent.handle_event(event)
    assert result_events == []
    agent._state_store.update_agent_state.assert_awaited_once_with(
        "dev-agent", status="working", current_task="task_001"
    )
