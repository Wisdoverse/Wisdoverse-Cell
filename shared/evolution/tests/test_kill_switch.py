"""Tests for evolution kill switch — TDD: written before implementation."""

from unittest.mock import AsyncMock

import pytest

from shared.evolution.kill_switch import KillSwitch

REDIS_KEY = "evolution:enabled"


class TestKillSwitchIsEnabled:
    """is_enabled() reflects the Redis flag state."""

    @pytest.mark.asyncio
    async def test_enabled_by_default_when_key_missing(self):
        """If the key is absent (None), evolution is ON by default."""
        redis = AsyncMock()
        redis.get.return_value = None

        ks = KillSwitch(redis)
        assert await ks.is_enabled() is True
        redis.get.assert_called_once_with(REDIS_KEY)

    @pytest.mark.asyncio
    async def test_disabled_when_flag_is_false_bytes(self):
        """Flag stored as b'false' → evolution is OFF."""
        redis = AsyncMock()
        redis.get.return_value = b"false"

        ks = KillSwitch(redis)
        assert await ks.is_enabled() is False

    @pytest.mark.asyncio
    async def test_disabled_when_flag_is_false_string(self):
        """Flag stored as 'false' string → evolution is OFF."""
        redis = AsyncMock()
        redis.get.return_value = "false"

        ks = KillSwitch(redis)
        assert await ks.is_enabled() is False

    @pytest.mark.asyncio
    async def test_enabled_when_flag_is_true(self):
        """Flag stored as b'true' → evolution is ON."""
        redis = AsyncMock()
        redis.get.return_value = b"true"

        ks = KillSwitch(redis)
        assert await ks.is_enabled() is True

    @pytest.mark.asyncio
    async def test_fail_safe_returns_false_on_connection_error(self):
        """Redis unreachable → fail-safe: disable evolution (return False)."""
        redis = AsyncMock()
        redis.get.side_effect = ConnectionError("Redis connection refused")

        ks = KillSwitch(redis)
        assert await ks.is_enabled() is False

    @pytest.mark.asyncio
    async def test_fail_safe_returns_false_on_generic_exception(self):
        """Any Redis exception → fail-safe: disable evolution (return False)."""
        redis = AsyncMock()
        redis.get.side_effect = Exception("Redis timeout")

        ks = KillSwitch(redis)
        assert await ks.is_enabled() is False


class TestKillSwitchDisable:
    """disable() writes 'false' to Redis."""

    @pytest.mark.asyncio
    async def test_disable_sets_flag_to_false(self):
        """disable() stores 'false' in the Redis key."""
        redis = AsyncMock()

        ks = KillSwitch(redis)
        await ks.disable()

        redis.set.assert_called_once_with(REDIS_KEY, "false")

    @pytest.mark.asyncio
    async def test_disable_accepts_reason_string(self):
        """disable(reason=...) still sets the flag correctly."""
        redis = AsyncMock()

        ks = KillSwitch(redis)
        await ks.disable(reason="emergency rollback")

        redis.set.assert_called_once_with(REDIS_KEY, "false")

    @pytest.mark.asyncio
    async def test_disable_makes_is_enabled_return_false(self):
        """After disable(), is_enabled() returns False."""
        redis = AsyncMock()
        redis.get.return_value = b"false"

        ks = KillSwitch(redis)
        await ks.disable(reason="test")

        assert await ks.is_enabled() is False


class TestKillSwitchEnable:
    """enable() writes 'true' to Redis."""

    @pytest.mark.asyncio
    async def test_enable_sets_flag_to_true(self):
        """enable() stores 'true' in the Redis key."""
        redis = AsyncMock()

        ks = KillSwitch(redis)
        await ks.enable()

        redis.set.assert_called_once_with(REDIS_KEY, "true")

    @pytest.mark.asyncio
    async def test_enable_makes_is_enabled_return_true(self):
        """After enable(), is_enabled() returns True."""
        redis = AsyncMock()
        redis.get.return_value = b"true"

        ks = KillSwitch(redis)
        await ks.enable()

        assert await ks.is_enabled() is True
