"""Tests for Coordinator think engine."""
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_think_returns_decision_list():
    from agents.orchestration.coordinator.core.models import Decision
    from agents.orchestration.coordinator.core.think import think

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="""{
        "decisions": [
            {
                "target_agent": "requirement-manager",
                "action": "dispatch_task",
                "task_id": "task_001",
                "instruction": "Produce PRD for @mention feature",
                "workflow_id": "wf_001",
                "reasoning": "New feature request, needs PRD first"
            }
        ]
    }""")

    context = {
        "scratchpad": "",
        "agent_states": {},
        "incoming_event": {
            "kind": "command",
            "data": {
                "command_id": "cmd_001",
                "intent": "new feature",
                "original_message": "新功能",
                "user_id": "u1",
                "user_name": "Alice",
            },
        },
        "pending_decisions": [],
    }

    decisions = await think(context, llm=mock_llm)
    assert len(decisions) == 1
    assert isinstance(decisions[0], Decision)
    assert decisions[0].target_agent == "requirement-manager"
    mock_llm.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_think_handles_empty_response():
    from agents.orchestration.coordinator.core.think import think

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value='{"decisions": []}')

    decisions = await think({"scratchpad": "", "agent_states": {}, "incoming_event": {"kind": "event", "data": {}}, "pending_decisions": []}, llm=mock_llm)
    assert decisions == []


@pytest.mark.asyncio
async def test_think_handles_malformed_json():
    from agents.orchestration.coordinator.core.think import think

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="not json at all")

    decisions = await think({"scratchpad": "", "agent_states": {}, "incoming_event": {"kind": "event", "data": {}}, "pending_decisions": []}, llm=mock_llm)
    assert decisions == []
