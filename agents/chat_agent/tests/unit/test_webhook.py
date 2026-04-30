"""
Unit Tests - Webhook dedup and Challenge verification

Tests for Redis-based message deduplication and challenge response.
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_redis():
    """Mock the Redis client used by _is_duplicate."""
    mock_r = AsyncMock()
    with patch("agents.chat_agent.api.webhook._get_redis", return_value=mock_r):
        yield mock_r


@pytest.mark.asyncio
async def test_is_duplicate_first_time(mock_redis):
    """First time receiving a message - not a duplicate (Redis SET nx returns True)."""
    from agents.chat_agent.api.webhook import _is_duplicate

    mock_redis.set = AsyncMock(return_value=True)  # nx=True succeeds -> key was set
    result = await _is_duplicate("msg_001")
    assert result is False
    mock_redis.set.assert_awaited_once_with("chat:dedup:msg_001", "1", nx=True, ex=300)


@pytest.mark.asyncio
async def test_is_duplicate_second_time(mock_redis):
    """Same message seen again - duplicate (Redis SET nx returns None/False)."""
    from agents.chat_agent.api.webhook import _is_duplicate

    mock_redis.set = AsyncMock(return_value=None)  # nx=True fails -> key already existed
    result = await _is_duplicate("msg_002")
    assert result is True


def test_challenge_response():
    """ChallengeResponse correctly echoes back the challenge value."""
    from agents.chat_agent.api.schemas import ChallengeResponse

    resp = ChallengeResponse(challenge="test_token_abc")
    assert resp.challenge == "test_token_abc"
    assert resp.model_dump() == {"challenge": "test_token_abc"}
