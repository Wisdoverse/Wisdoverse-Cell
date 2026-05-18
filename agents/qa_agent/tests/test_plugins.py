"""QA runtime plugin tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestQAOutboxDispatcherPlugin:
    @pytest.mark.asyncio
    async def test_dispatch_once_calls_agent_outbox_dispatcher(self):
        from agents.qa_agent.app.plugins.outbox_dispatcher import (
            QAOutboxDispatcherPlugin,
        )

        plugin = QAOutboxDispatcherPlugin(interval=100, batch_size=7)
        runtime = MagicMock()
        runtime.agent.publish_pending_qa_events = AsyncMock(
            return_value={"total": 1, "published": 1, "failed": 0}
        )

        await plugin._dispatch_once(runtime)

        runtime.agent.publish_pending_qa_events.assert_awaited_once_with(limit=7)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "down"

    @pytest.mark.asyncio
    async def test_health_ok_when_running(self):
        from agents.qa_agent.app.plugins.outbox_dispatcher import (
            QAOutboxDispatcherPlugin,
        )

        runtime = MagicMock()
        runtime.agent.publish_pending_qa_events = AsyncMock(
            return_value={"total": 0, "published": 0, "failed": 0}
        )

        plugin = QAOutboxDispatcherPlugin(interval=100)
        await plugin.startup(runtime)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "ok"
        await plugin.shutdown(runtime)
