"""Tests for user-interaction scheduler application use cases."""

from unittest.mock import AsyncMock

import pytest

from agents.chat_agent.core.scheduler_use_cases import (
    ChatAgentSchedulerUseCase,
)


@pytest.mark.asyncio
async def test_run_scheduled_action_forwards_action_name() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"status": "ok"}

    result = await ChatAgentSchedulerUseCase(agent).run_scheduled_action(
        "cleanup_conversations"
    )

    assert result == {"status": "ok"}
    agent.handle_request.assert_awaited_once_with(
        {"action": "cleanup_conversations"}
    )
