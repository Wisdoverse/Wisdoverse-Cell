from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.orchestration.coordinator.core.event_use_cases import (
    CoordinatorEventUseCase,
)
from services.orchestration.coordinator.core.models import Decision
from shared.schemas.event import Event, EventTypes


def _scratchpad() -> MagicMock:
    scratchpad = MagicMock()
    scratchpad.read_incremental = AsyncMock(return_value="status ok")
    scratchpad.update = AsyncMock()
    scratchpad.should_compact = MagicMock(return_value=False)
    scratchpad.compact = AsyncMock()
    return scratchpad


def _state_store() -> MagicMock:
    state_store = MagicMock()
    state_store.update_agent_state = AsyncMock()
    state_store.get_agent_states = AsyncMock(
        return_value={
            "dev-agent": SimpleNamespace(
                model_dump=lambda: {
                    "agent_id": "dev-agent",
                    "status": "idle",
                }
            )
        }
    )
    state_store.get_pending_decisions = AsyncMock(return_value=[])
    state_store.persist = AsyncMock()
    return state_store


@pytest.mark.asyncio
async def test_progress_event_updates_state_without_thinking() -> None:
    scratchpad = _scratchpad()
    state_store = _state_store()
    thinker = AsyncMock(return_value=[])
    use_case = CoordinatorEventUseCase(
        scratchpad=scratchpad,
        state_store=state_store,
        thinker=thinker,
    )

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.TASK_PROGRESS,
            source_agent="dev-agent",
            payload={
                "task_id": "task_1",
                "agent_id": "dev-agent",
                "tool_use_count": 1,
                "llm_token_count": 10,
            },
        )
    )

    assert result == []
    state_store.update_agent_state.assert_awaited_once_with(
        "dev-agent",
        status="working",
        current_task="task_1",
    )
    scratchpad.read_incremental.assert_not_awaited()
    thinker.assert_not_awaited()
    state_store.persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_event_builds_context_persists_and_emits_decision_events() -> None:
    scratchpad = _scratchpad()
    state_store = _state_store()
    decision = Decision(
        target_agent="requirement-manager",
        action="dispatch_task",
        task_id="task_1",
        instruction="Create PRD",
        workflow_id="wf_1",
    )
    thinker = AsyncMock(return_value=[decision])
    use_case = CoordinatorEventUseCase(
        scratchpad=scratchpad,
        state_store=state_store,
        thinker=thinker,
    )

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.COORDINATOR_COMMAND,
            source_agent="chat-agent",
            payload={
                "command_id": "cmd_1",
                "intent": "new feature",
                "original_message": "build it",
                "user_id": "u_1",
                "user_name": "Alice",
            },
            trace_id="trace_1",
        )
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.COORDINATOR_DISPATCH
    assert result[0].metadata.trace_id == "trace_1"
    assert result[0].payload["target_agent"] == "requirement-manager"

    context = thinker.await_args.args[0]
    assert context["scratchpad"] == "status ok"
    assert context["incoming_event"]["kind"] == "command"
    assert context["incoming_event"]["data"]["command_id"] == "cmd_1"
    assert context["agent_states"]["dev-agent"]["status"] == "idle"
    scratchpad.update.assert_awaited_once()
    persisted = state_store.persist.await_args.args[0]
    assert persisted[0].trace_id == "trace_1"


@pytest.mark.asyncio
async def test_existing_decision_trace_id_is_preserved() -> None:
    decision = Decision(
        target_agent="chat-agent",
        action="respond",
        task_id="task_1",
        instruction="Reply",
        trace_id="decision_trace",
        command_id="cmd_1",
        summary="done",
    )
    use_case = CoordinatorEventUseCase(
        scratchpad=_scratchpad(),
        state_store=_state_store(),
        thinker=AsyncMock(return_value=[decision]),
    )

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.COORDINATOR_COMMAND,
            source_agent="chat-agent",
            payload={
                "command_id": "cmd_1",
                "intent": "status",
                "original_message": "status",
                "user_id": "u_1",
                "user_name": "Alice",
            },
            trace_id="event_trace",
        )
    )

    assert result[0].metadata.trace_id == "decision_trace"
