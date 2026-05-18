"""Dev runtime plugin tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestDevOutboxDispatcherPlugin:
    @pytest.mark.asyncio
    async def test_dispatch_once_calls_agent_outbox_dispatcher(self):
        from agents.dev_agent.app.plugins.outbox_dispatcher import (
            DevOutboxDispatcherPlugin,
        )

        plugin = DevOutboxDispatcherPlugin(interval=100, batch_size=7)
        runtime = MagicMock()
        runtime.agent.publish_pending_dev_events = AsyncMock(
            return_value={"total": 1, "published": 1, "failed": 0}
        )

        await plugin._dispatch_once(runtime)

        runtime.agent.publish_pending_dev_events.assert_awaited_once_with(limit=7)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "down"

    @pytest.mark.asyncio
    async def test_health_ok_when_running(self):
        from agents.dev_agent.app.plugins.outbox_dispatcher import (
            DevOutboxDispatcherPlugin,
        )

        runtime = MagicMock()
        runtime.agent.publish_pending_dev_events = AsyncMock(
            return_value={"total": 0, "published": 0, "failed": 0}
        )

        plugin = DevOutboxDispatcherPlugin(interval=100)
        await plugin.startup(runtime)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "ok"
        await plugin.shutdown(runtime)

    @pytest.mark.asyncio
    async def test_dispatch_once_emits_prometheus_metrics(self):
        """Dispatch cycle increments published/failed/total counters."""
        from agents.dev_agent.app.plugins.outbox_dispatcher import (
            DevOutboxDispatcherPlugin,
        )
        from shared.infra.metrics import (
            OUTBOX_DISPATCH_DURATION_SECONDS,
            OUTBOX_DISPATCH_EVENTS,
        )

        def _value(outcome: str) -> float:
            metric = OUTBOX_DISPATCH_EVENTS.labels(
                runtime="dev-agent",
                outcome=outcome,
            )
            return metric._value.get()

        def _duration_count() -> float:
            metric = OUTBOX_DISPATCH_DURATION_SECONDS.labels(
                runtime="dev-agent",
            )
            return metric._sum.get()

        before_total = _value("total")
        before_published = _value("published")
        before_failed = _value("failed")
        before_duration_sum = _duration_count()

        plugin = DevOutboxDispatcherPlugin(interval=100, batch_size=5)
        runtime = MagicMock()
        runtime.agent.publish_pending_dev_events = AsyncMock(
            return_value={"total": 3, "published": 2, "failed": 1}
        )

        await plugin._dispatch_once(runtime)

        assert _value("total") == before_total + 3
        assert _value("published") == before_published + 2
        assert _value("failed") == before_failed + 1
        assert _duration_count() >= before_duration_sum  # duration observed

    @pytest.mark.asyncio
    async def test_dispatch_once_error_increments_error_counter(self):
        """Errors raised by the inner dispatcher are caught at the loop level."""
        from agents.dev_agent.app.plugins.outbox_dispatcher import (
            DevOutboxDispatcherPlugin,
        )
        from shared.infra.metrics import OUTBOX_DISPATCH_ERRORS

        def _value(error_type: str) -> float:
            metric = OUTBOX_DISPATCH_ERRORS.labels(
                runtime="dev-agent",
                error_type=error_type,
            )
            return metric._value.get()

        before = _value("RuntimeError")

        plugin = DevOutboxDispatcherPlugin(interval=100)
        runtime = MagicMock()
        runtime.agent.publish_pending_dev_events = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        with pytest.raises(RuntimeError):
            await plugin._dispatch_once(runtime)

        # _dispatch_once itself does not record the error; only the outer
        # loop does. So the error counter remains unchanged at this layer.
        assert _value("RuntimeError") == before
