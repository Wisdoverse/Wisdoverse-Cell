from unittest.mock import AsyncMock

import pytest

from services.gateways.user_interaction.core.request_use_cases import (
    UserInteractionRequestUseCase,
)
from shared.core import UNKNOWN_ACTION_ERROR_CODE


def _use_case(
    *,
    chat: AsyncMock | None = None,
    history_store: AsyncMock | None = None,
    dispatch_morning_tasks: AsyncMock | None = None,
    collect_evening_progress: AsyncMock | None = None,
) -> UserInteractionRequestUseCase:
    return UserInteractionRequestUseCase(
        chat=chat or AsyncMock(),
        history_store=history_store or AsyncMock(),
        dispatch_morning_tasks=dispatch_morning_tasks or AsyncMock(),
        collect_evening_progress=collect_evening_progress or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_chat_action_delegates_to_chat_service() -> None:
    chat = AsyncMock()
    chat.chat = AsyncMock(return_value="reply")

    result = await _use_case(chat=chat).handle(
        {"action": "chat", "message": "hello", "user_id": "u_1"}
    )

    assert result == {"reply": "reply"}
    chat.chat.assert_awaited_once_with(message="hello", user_id="u_1")


@pytest.mark.asyncio
async def test_chat_user_assistant_builds_context_for_chat_service() -> None:
    chat = AsyncMock()
    chat.chat_with_user_assistant = AsyncMock(return_value="assistant reply")

    result = await _use_case(chat=chat).handle(
        {
            "action": "chat_user_assistant",
            "message": "status",
            "user_id": "u_2",
            "user_name": "Alice",
            "chat_id": "oc_1",
            "chat_type": "group",
        }
    )

    assert result == {"reply": "assistant reply"}
    chat.chat_with_user_assistant.assert_awaited_once_with(
        message="status",
        user_id="u_2",
        user_name="Alice",
        context={
            "user_id": "u_2",
            "user_name": "Alice",
            "chat_id": "oc_1",
            "chat_type": "group",
        },
    )


@pytest.mark.asyncio
async def test_clear_history_delegates_to_chat_service() -> None:
    chat = AsyncMock()
    chat.clear_history = AsyncMock()

    result = await _use_case(chat=chat).handle(
        {"action": "clear_history", "user_id": "u_1"}
    )

    assert result == {"status": "cleared"}
    chat.clear_history.assert_awaited_once_with("u_1")


@pytest.mark.asyncio
async def test_cleanup_conversations_uses_history_store_port() -> None:
    history_store = AsyncMock()
    history_store.delete_inactive = AsyncMock(return_value=5)

    result = await _use_case(history_store=history_store).handle(
        {"action": "cleanup_conversations"}
    )

    assert result == {"status": "ok", "deleted": 5}
    history_store.delete_inactive.assert_awaited_once_with(days=30)


@pytest.mark.asyncio
async def test_scheduled_daily_actions_delegate_to_injected_commands() -> None:
    dispatch = AsyncMock()
    collect = AsyncMock()
    use_case = _use_case(
        dispatch_morning_tasks=dispatch,
        collect_evening_progress=collect,
    )

    assert await use_case.handle({"action": "dispatch_morning_tasks"}) == {
        "status": "ok"
    }
    assert await use_case.handle({"action": "collect_evening_progress"}) == {
        "status": "ok"
    }
    dispatch.assert_awaited_once_with()
    collect.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unknown_action_uses_shared_request_result_contract() -> None:
    result = await _use_case().handle({"action": "unknown"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }
