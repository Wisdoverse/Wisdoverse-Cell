from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGrpcPlugin:
    @pytest.mark.asyncio
    async def test_startup_calls_factory(self):
        from agents.requirement_manager.app.plugins.grpc import GrpcPlugin

        mock_factory = AsyncMock(return_value=MagicMock())
        plugin = GrpcPlugin(server_factory=mock_factory)
        runtime = MagicMock()
        runtime.agent = MagicMock()
        await plugin.startup(runtime)
        mock_factory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_ok_when_started(self):
        from agents.requirement_manager.app.plugins.grpc import GrpcPlugin

        plugin = GrpcPlugin(server_factory=AsyncMock(return_value=MagicMock()))
        await plugin.startup(MagicMock())
        result = await plugin.health_check()
        assert result["server"].status == "ok"

    @pytest.mark.asyncio
    async def test_health_down_when_not_started(self):
        from agents.requirement_manager.app.plugins.grpc import GrpcPlugin

        plugin = GrpcPlugin()
        result = await plugin.health_check()
        assert result["server"].status == "down"


class TestSessionTimeoutPlugin:
    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        from agents.requirement_manager.app.plugins.session_timeout import (
            SessionTimeoutPlugin,
        )

        with patch("agents.requirement_manager.app.plugins.session_timeout.settings") as s:
            s.feishu_message_recording_enabled = False
            plugin = SessionTimeoutPlugin()
            await plugin.startup(MagicMock())
            result = await plugin.health_check()
            assert result == {}

    @pytest.mark.asyncio
    async def test_health_ok_when_running(self):
        from agents.requirement_manager.app.plugins.session_timeout import (
            SessionTimeoutPlugin,
        )

        with (
            patch("agents.requirement_manager.app.plugins.session_timeout.settings") as s,
            patch(
                "agents.requirement_manager.app.plugins.session_timeout.get_session_manager"
            ) as gsm,
        ):
            s.feishu_message_recording_enabled = True
            gsm.return_value = MagicMock()
            plugin = SessionTimeoutPlugin(interval=100)
            await plugin.startup(MagicMock())
            result = await plugin.health_check()
            assert result["checker"].status == "ok"
            await plugin.shutdown(MagicMock())


class TestRequirementOutboxDispatcherPlugin:
    @pytest.mark.asyncio
    async def test_dispatch_once_calls_agent_outbox_dispatcher(self):
        from agents.requirement_manager.app.plugins.outbox_dispatcher import (
            RequirementOutboxDispatcherPlugin,
        )

        plugin = RequirementOutboxDispatcherPlugin(interval=100, batch_size=7)
        runtime = MagicMock()
        runtime.agent.publish_pending_requirement_events = AsyncMock(
            return_value={"total": 1, "published": 1, "failed": 0}
        )

        await plugin._dispatch_once(runtime)

        runtime.agent.publish_pending_requirement_events.assert_awaited_once_with(limit=7)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "down"

    @pytest.mark.asyncio
    async def test_health_ok_when_running(self):
        from agents.requirement_manager.app.plugins.outbox_dispatcher import (
            RequirementOutboxDispatcherPlugin,
        )

        runtime = MagicMock()
        runtime.agent.publish_pending_requirement_events = AsyncMock(
            return_value={"total": 0, "published": 0, "failed": 0}
        )

        plugin = RequirementOutboxDispatcherPlugin(interval=100)
        await plugin.startup(runtime)
        result = await plugin.health_check()
        assert result["dispatcher"].status == "ok"
        await plugin.shutdown(runtime)


class TestFeishuGatewayPlugin:
    @pytest.mark.asyncio
    async def test_skips_when_feishu_disabled(self):
        from agents.requirement_manager.app.plugins.feishu_gateway import FeishuGatewayPlugin

        with patch("agents.requirement_manager.app.plugins.feishu_gateway.settings") as s:
            s.feishu_enabled = False
            plugin = FeishuGatewayPlugin()
            await plugin.startup(MagicMock())
            result = await plugin.health_check()
            assert result == {}


class TestChannelRegistryPlugin:
    @pytest.mark.asyncio
    async def test_no_channels_returns_empty(self):
        from agents.requirement_manager.app.plugins.channel_registry import (
            ChannelRegistryPlugin,
        )

        with patch("agents.requirement_manager.app.plugins.channel_registry.settings") as s:
            s.feishu_enabled = False
            s.wecom_enabled = False
            s.openclaw_enabled = False
            plugin = ChannelRegistryPlugin()
            await plugin.startup(MagicMock())
            result = await plugin.health_check()
            assert result == {}

    @pytest.mark.asyncio
    async def test_health_ok_when_expected_channel_registered(self):
        from agents.requirement_manager.app.plugins.channel_registry import (
            ChannelRegistryPlugin,
        )
        from shared.core.channels import ChannelRegistry

        ChannelRegistry.clear()
        try:
            channel = MagicMock()
            channel.channel_name = "feishu"
            ChannelRegistry.register(channel)

            plugin = ChannelRegistryPlugin()
            plugin._expected_channels = 1
            result = await plugin.health_check()

            assert result["channels"].status == "ok"
        finally:
            ChannelRegistry.clear()
