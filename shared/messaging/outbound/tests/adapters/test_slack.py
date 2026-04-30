"""Tests for Slack adapter."""
pytest = __import__("pytest")
pytest.importorskip("slack_bolt", reason="slack-bolt not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from shared.messaging.outbound.adapters._stable.slack import SlackAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import OutboundMessage


class TestSlackAdapterAttributes:
    def test_channel_id(self):
        adapter = SlackAdapter(token="test-slack-token")
        assert adapter.channel_id == "slack"

    def test_channel_name(self):
        adapter = SlackAdapter(token="test-slack-token")
        assert adapter.channel_name == "Slack"

    def test_status_is_stable(self):
        adapter = SlackAdapter(token="test-slack-token")
        assert adapter.status == ChannelStatus.STABLE

    def test_capabilities(self):
        adapter = SlackAdapter(token="test-slack-token")
        assert ChannelCapability.TEXT in adapter.capabilities
        assert ChannelCapability.RICH_MEDIA in adapter.capabilities
        assert ChannelCapability.EDIT_MESSAGE in adapter.capabilities
        assert ChannelCapability.DELETE_MESSAGE in adapter.capabilities
        assert ChannelCapability.REACTIONS in adapter.capabilities
        assert ChannelCapability.TYPING_INDICATOR in adapter.capabilities
        assert ChannelCapability.READ_RECEIPTS in adapter.capabilities
        assert ChannelCapability.GROUP_MANAGEMENT in adapter.capabilities
        assert ChannelCapability.WEBHOOKS in adapter.capabilities


class TestSlackAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_initializes_app(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_app = MagicMock()
            mock_app.client = AsyncMock()
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            await adapter.connect()

            mock_app_class.assert_called_once_with(token="test-slack-token")

    @pytest.mark.asyncio
    async def test_disconnect_clears_app(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_app = MagicMock()
            mock_app.client = AsyncMock()
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            await adapter.connect()
            await adapter.disconnect()

            assert adapter._app is None


class TestSlackAdapterSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_client = AsyncMock()
            mock_client.chat_postMessage.return_value = {
                "ok": True,
                "ts": "1234567890.123456",
            }
            mock_app = MagicMock()
            mock_app.client = mock_client
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            await adapter.connect()

            message = OutboundMessage(
                channel_id="slack",
                target_chat_id="C12345678",
                content="Hello Slack",
            )

            result = await adapter.send_message(message)

            assert result.success is True
            assert result.platform_message_id == "1234567890.123456"
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        adapter = SlackAdapter(token="test-slack-token")
        message = OutboundMessage(
            channel_id="slack",
            target_chat_id="C12345678",
            content="Hello",
        )
        result = await adapter.send_message(message)
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"


class TestSlackAdapterEditDelete:
    @pytest.mark.asyncio
    async def test_edit_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_client = AsyncMock()
            mock_client.chat_update.return_value = {"ok": True}
            mock_app = MagicMock()
            mock_app.client = mock_client
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            adapter._channel_cache["1234567890.123456"] = "C12345678"
            await adapter.connect()

            result = await adapter.edit_message("1234567890.123456", "New content")

            assert result is True
            mock_client.chat_update.assert_called_once_with(
                channel="C12345678",
                ts="1234567890.123456",
                text="New content",
            )

    @pytest.mark.asyncio
    async def test_delete_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_client = AsyncMock()
            mock_client.chat_delete.return_value = {"ok": True}
            mock_app = MagicMock()
            mock_app.client = mock_client
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            adapter._channel_cache["1234567890.123456"] = "C12345678"
            await adapter.connect()

            result = await adapter.delete_message("1234567890.123456")

            assert result is True
            mock_client.chat_delete.assert_called_once_with(
                channel="C12345678",
                ts="1234567890.123456",
            )


class TestSlackAdapterReactions:
    @pytest.mark.asyncio
    async def test_add_reaction(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_client = AsyncMock()
            mock_client.reactions_add.return_value = {"ok": True}
            mock_app = MagicMock()
            mock_app.client = mock_client
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            adapter._channel_cache["1234567890.123456"] = "C12345678"
            await adapter.connect()

            result = await adapter.add_reaction("1234567890.123456", "thumbsup")

            assert result is True
            mock_client.reactions_add.assert_called_once_with(
                channel="C12345678",
                timestamp="1234567890.123456",
                name="thumbsup",
            )

    @pytest.mark.asyncio
    async def test_add_reaction_not_connected(self):
        adapter = SlackAdapter(token="test-slack-token")
        result = await adapter.add_reaction("1234567890.123456", "thumbsup")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_reaction(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.slack.AsyncApp"
        ) as mock_app_class:
            mock_client = AsyncMock()
            mock_client.reactions_remove.return_value = {"ok": True}
            mock_app = MagicMock()
            mock_app.client = mock_client
            mock_app_class.return_value = mock_app

            adapter = SlackAdapter(token="test-slack-token")
            adapter._channel_cache["1234567890.123456"] = "C12345678"
            await adapter.connect()

            result = await adapter.remove_reaction("1234567890.123456", "thumbsup")

            assert result is True
            mock_client.reactions_remove.assert_called_once_with(
                channel="C12345678",
                timestamp="1234567890.123456",
                name="thumbsup",
            )

    @pytest.mark.asyncio
    async def test_remove_reaction_not_connected(self):
        adapter = SlackAdapter(token="test-slack-token")
        result = await adapter.remove_reaction("1234567890.123456", "thumbsup")
        assert result is False
