"""Unit tests for user interaction persistence helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gateways.user_interaction.db.repository import (
    MAX_CONVERSATION_BYTES,
    ConversationRepository,
    _hash_user_id,
)


@pytest.mark.asyncio
async def test_conversation_trim_log_uses_user_hash() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    repo = ConversationRepository(session)
    messages = [
        {"role": "user", "content": "x" * (MAX_CONVERSATION_BYTES + 1)},
        {"role": "assistant", "content": "ok"},
    ]

    with patch("services.gateways.user_interaction.db.repository.logger") as logger:
        await repo.save("ou_raw_user", messages)

    warning = logger.warning.call_args
    assert warning.args == ("conversation_trimmed",)
    assert warning.kwargs["user_hash"] == _hash_user_id("ou_raw_user")
    assert "user_id" not in warning.kwargs
