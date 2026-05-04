"""Tests for CoordinatorAgent with think engine wired in."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_coordinator_calls_llm_on_command():
    from services.orchestration.coordinator.service.agent import CoordinatorAgent

    agent = CoordinatorAgent()
    agent._scratchpad = MagicMock()
    agent._scratchpad.read_incremental = AsyncMock(return_value="Status OK")
    agent._scratchpad.update = AsyncMock()
    agent._scratchpad.should_compact = MagicMock(return_value=False)
    agent._scratchpad.initialize = AsyncMock()
    agent._state_store = MagicMock()
    agent._state_store.get_agent_states = AsyncMock(return_value={})
    agent._state_store.get_pending_decisions = AsyncMock(return_value=[])
    agent._state_store.persist = AsyncMock()

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value='{"decisions": [{"target_agent": "requirement-manager", "action": "dispatch_task", "task_id": "t1", "instruction": "Make PRD"}]}')
    agent._llm = mock_llm

    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "new feature",
            "original_message": "Build it",
            "user_id": "u1",
            "user_name": "Alice",
        },
    )
    results = await agent.handle_event(event)
    assert len(results) == 1
    assert results[0].event_type == EventTypes.COORDINATOR_DISPATCH
    mock_llm.complete.assert_awaited_once()
