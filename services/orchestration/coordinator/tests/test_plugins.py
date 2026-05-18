"""Coordinator runtime plugin tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestCoordinatorOutboxDispatcherPlugin:
    @pytest.mark.asyncio
    async def test_dispatch_once_calls_agent_outbox_dispatcher(self):
        from services.orchestration.coordinator.app.plugins.outbox_dispatcher import (
            CoordinatorOutboxDispatcherPlugin,
        )

        plugin = CoordinatorOutboxDispatcherPlugin(interval=100, batch_size=7)
        runtime = MagicMock()
        runtime.agent.publish_pending_coordinator_events = AsyncMock(
            return_value={"total": 1, "published": 1, "failed": 0}
        )

        await plugin._dispatch_once(runtime)

        runtime.agent.publish_pending_coordinator_events.assert_awaited_once_with(limit=7)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "down"

    @pytest.mark.asyncio
    async def test_health_ok_when_running(self):
        from services.orchestration.coordinator.app.plugins.outbox_dispatcher import (
            CoordinatorOutboxDispatcherPlugin,
        )

        runtime = MagicMock()
        runtime.agent.publish_pending_coordinator_events = AsyncMock(
            return_value={"total": 0, "published": 0, "failed": 0}
        )

        plugin = CoordinatorOutboxDispatcherPlugin(interval=100)
        await plugin.startup(runtime)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "ok"
        await plugin.shutdown(runtime)
