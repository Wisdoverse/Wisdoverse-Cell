"""Tests for AgentStatusPlugin and build_status().

Covers:
1. Plugin name and identity
2. Health check always returns empty (always healthy)
3. contribute_status returns uptime + started_at
4. build_status shape with running runtime
5. Loop breaker data from Redis parsed correctly
6. Plugin contributions appear in status
7. Graceful handling of missing Redis data
8. startup() initializes own Redis client
9. shutdown() closes Redis client gracefully
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.app.plugins.status_plugin import AgentStatusPlugin, build_status


class TestAgentStatusPlugin:
    def test_plugin_name(self):
        plugin = AgentStatusPlugin()
        assert plugin.name == "agent-status"

    def test_init_redis_is_none(self):
        plugin = AgentStatusPlugin()
        assert plugin._redis is None

    @pytest.mark.asyncio
    async def test_health_check_always_ok(self):
        plugin = AgentStatusPlugin()
        result = await plugin.health_check()
        assert result == {}

    def test_contribute_status_returns_uptime(self):
        plugin = AgentStatusPlugin()
        # Simulate startup having been called
        plugin._started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        status = plugin.contribute_status()
        assert status["uptime_seconds"] > 0
        assert "started_at" in status
        assert status["started_at"] == "2026-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_startup_creates_redis_client(self):
        """startup() should create a Redis client via redis.asyncio."""
        fake_redis = MagicMock()
        fake_aioredis = MagicMock()
        fake_aioredis.from_url.return_value = fake_redis

        plugin = AgentStatusPlugin()
        runtime = MagicMock()

        # redis.asyncio is imported as a submodule of redis, so we need both entries
        fake_redis_pkg = MagicMock()
        fake_redis_pkg.asyncio = fake_aioredis
        with patch.dict(
            "sys.modules",
            {"redis": fake_redis_pkg, "redis.asyncio": fake_aioredis},
        ):
            await plugin.startup(runtime)

        assert plugin._started_at is not None
        assert plugin._redis is fake_redis
        fake_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_redis_failure_graceful(self):
        """If Redis init fails, plugin should still start (redis stays None)."""
        plugin = AgentStatusPlugin()
        runtime = MagicMock()

        with patch.dict("sys.modules", {"redis.asyncio": None, "redis": None}):
            # Force import to fail by removing module
            import sys
            saved = sys.modules.get("redis.asyncio")
            sys.modules["redis.asyncio"] = None
            try:
                await plugin.startup(runtime)
            finally:
                if saved is not None:
                    sys.modules["redis.asyncio"] = saved
                else:
                    sys.modules.pop("redis.asyncio", None)

        assert plugin._started_at is not None
        assert plugin._redis is None

    @pytest.mark.asyncio
    async def test_shutdown_closes_redis(self):
        """shutdown() should close the Redis client."""
        plugin = AgentStatusPlugin()
        plugin._redis = AsyncMock()
        runtime = MagicMock()

        await plugin.shutdown(runtime)

        plugin._redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_no_redis_noop(self):
        """shutdown() with no Redis client should not raise."""
        plugin = AgentStatusPlugin()
        runtime = MagicMock()

        await plugin.shutdown(runtime)  # Should not raise

    @pytest.mark.asyncio
    async def test_shutdown_redis_close_error_swallowed(self):
        """shutdown() should swallow errors from aclose()."""
        plugin = AgentStatusPlugin()
        plugin._redis = AsyncMock()
        plugin._redis.aclose.side_effect = RuntimeError("close failed")
        runtime = MagicMock()

        await plugin.shutdown(runtime)  # Should not raise


class TestBuildStatus:
    @pytest.mark.asyncio
    async def test_basic_status_shape(self):
        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")

        assert status["agent_id"] == "test-agent"
        assert status["state"] == "running"
        assert status["loop_breaker"] == {}
        assert status["plugins"] == {}

    @pytest.mark.asyncio
    async def test_loop_breaker_from_redis(self):
        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={
            "state": "half_open",
            "no_progress_count": "2",
            "same_error_count": "1",
            "output_decline_count": "0",
            "total_opens": "3",
        })

        status = await build_status(runtime, redis, agent_id="test-agent")

        lb = status["loop_breaker"]
        assert lb["state"] == "half_open"
        assert lb["no_progress_count"] == "2"
        assert lb["same_error_count"] == "1"
        assert lb["output_decline_count"] == "0"
        assert lb["total_opens"] == "3"

    @pytest.mark.asyncio
    async def test_loop_breaker_from_redis_bytes_keys(self):
        """Redis may return bytes keys when decode_responses is False."""
        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={
            b"state": b"closed",
            b"no_progress_count": b"0",
        })

        status = await build_status(runtime, redis, agent_id="test-agent")

        lb = status["loop_breaker"]
        assert lb["state"] == "closed"
        assert lb["no_progress_count"] == "0"

    @pytest.mark.asyncio
    async def test_plugin_contributions(self):
        mock_plugin = MagicMock()
        mock_plugin.name = "my-plugin"
        mock_plugin.contribute_status.return_value = {"version": "1.0"}

        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = [mock_plugin]

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")

        assert "my-plugin" in status["plugins"]
        assert status["plugins"]["my-plugin"] == {"version": "1.0"}

    @pytest.mark.asyncio
    async def test_plugin_contribute_status_exception_handled(self):
        """Plugin exceptions should be caught, not propagate."""
        bad_plugin = MagicMock()
        bad_plugin.name = "bad-plugin"
        bad_plugin.contribute_status.side_effect = RuntimeError("boom")

        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = [bad_plugin]

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")

        # Should not crash — bad plugin just omitted
        assert "bad-plugin" not in status["plugins"]

    @pytest.mark.asyncio
    async def test_missing_redis_data_graceful(self):
        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")

        assert status["loop_breaker"] == {}

    @pytest.mark.asyncio
    async def test_state_starting_when_not_started(self):
        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = False
        runtime._plugins = []

        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})

        status = await build_status(runtime, redis, agent_id="test-agent")

        assert status["state"] == "starting"

    @pytest.mark.asyncio
    async def test_none_redis_graceful(self):
        """build_status should handle redis=None gracefully."""
        runtime = MagicMock()
        runtime.agent_id = "test-agent"
        runtime.is_started = True
        runtime._plugins = []

        status = await build_status(runtime, None, agent_id="test-agent")

        assert status["loop_breaker"] == {}
