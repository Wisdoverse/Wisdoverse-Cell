from unittest.mock import AsyncMock

import pytest

from agents.chat_agent.core.request_use_cases import ChatAgentRequestUseCase


def _use_case(*, history_store: AsyncMock) -> ChatAgentRequestUseCase:
    return ChatAgentRequestUseCase(
        chat=None,
        history_store=history_store,
        dispatch_morning_tasks=AsyncMock(),
        collect_evening_progress=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_get_conversation_history_uses_chat_agent_history_store() -> None:
    history_store = AsyncMock()
    history_store.get_by_user = AsyncMock(return_value=[{"role": "user"}])

    result = await _use_case(history_store=history_store).handle(
        {
            "action": "get_conversation_history",
            "user_id": "u_1",
        }
    )

    assert result == {"user_id": "u_1", "messages": [{"role": "user"}]}
    history_store.get_by_user.assert_awaited_once_with("u_1")


@pytest.mark.asyncio
async def test_list_daily_progress_uses_chat_agent_query_use_case() -> None:
    history_store = AsyncMock()
    daily_progress_queries = AsyncMock()
    daily_progress_queries.list_progress_response = AsyncMock(
        return_value={"entries": [], "total": 0}
    )
    use_case = ChatAgentRequestUseCase(
        chat=None,
        history_store=history_store,
        dispatch_morning_tasks=AsyncMock(),
        collect_evening_progress=AsyncMock(),
        daily_progress_queries=daily_progress_queries,
    )

    result = await use_case.handle(
        {
            "action": "list_daily_progress",
            "target_date": None,
            "user_id": "u_1",
            "days": 2,
        }
    )

    assert result == {"entries": [], "total": 0}
    daily_progress_queries.list_progress_response.assert_awaited_once_with(
        target_date=None,
        user_id="u_1",
        days=2,
    )
