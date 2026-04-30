"""Tests for Telegram adapter."""
pytest = __import__("pytest")
pytest.importorskip("telegram", reason="python-telegram-bot not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from shared.messaging.outbound.adapters._stable.telegram import TelegramAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import OutboundMessage


class TestTelegramAdapterAttributes:
    def test_channel_id(self):
        adapter = TelegramAdapter(token="test_token")
        assert adapter.channel_id == "telegram"

    def test_channel_name(self):
        adapter = TelegramAdapter(token="test_token")
        assert adapter.channel_name == "Telegram"

    def test_status_is_stable(self):
        adapter = TelegramAdapter(token="test_token")
        assert adapter.status == ChannelStatus.STABLE

    def test_capabilities(self):
        adapter = TelegramAdapter(token="test_token")
        assert ChannelCapability.TEXT in adapter.capabilities
        assert ChannelCapability.RICH_MEDIA in adapter.capabilities
        assert ChannelCapability.EDIT_MESSAGE in adapter.capabilities
        assert ChannelCapability.DELETE_MESSAGE in adapter.capabilities
        assert ChannelCapability.REACTIONS in adapter.capabilities
        assert ChannelCapability.TYPING_INDICATOR in adapter.capabilities


class TestTelegramAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_initializes_bot(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.telegram.Bot"
        ) as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot_class.return_value = mock_bot

            adapter = TelegramAdapter(token="test_token")
            await adapter.connect()

            mock_bot_class.assert_called_once_with(token="test_token")

    @pytest.mark.asyncio
    async def test_disconnect_stops_bot(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.telegram.Bot"
        ) as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot_class.return_value = mock_bot

            adapter = TelegramAdapter(token="test_token")
            await adapter.connect()
            await adapter.disconnect()

            mock_bot.shutdown.assert_called_once()


class TestTelegramAdapterSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.telegram.Bot"
        ) as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot.send_message.return_value = MagicMock(message_id=123)
            mock_bot_class.return_value = mock_bot

            adapter = TelegramAdapter(token="test_token")
            await adapter.connect()

            message = OutboundMessage(
                channel_id="telegram",
                target_chat_id="12345",
                content="Hello Telegram",
            )

            result = await adapter.send_message(message)

            assert result.success is True
            assert result.platform_message_id == "123"
            mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        adapter = TelegramAdapter(token="test_token")
        message = OutboundMessage(
            channel_id="telegram",
            target_chat_id="12345",
            content="Hello",
        )
        result = await adapter.send_message(message)
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"


class TestTelegramAdapterEditDelete:
    @pytest.mark.asyncio
    async def test_edit_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.telegram.Bot"
        ) as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot.edit_message_text.return_value = MagicMock()
            mock_bot_class.return_value = mock_bot

            adapter = TelegramAdapter(token="test_token")
            adapter._chat_id_cache["123"] = "12345"
            await adapter.connect()

            result = await adapter.edit_message("123", "New content")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.telegram.Bot"
        ) as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot.delete_message.return_value = True
            mock_bot_class.return_value = mock_bot

            adapter = TelegramAdapter(token="test_token")
            adapter._chat_id_cache["123"] = "12345"
            await adapter.connect()

            result = await adapter.delete_message("123")

            assert result is True


class TestTelegramAdapterTyping:
    @pytest.mark.asyncio
    async def test_send_typing_indicator(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.telegram.Bot"
        ) as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot_class.return_value = mock_bot

            adapter = TelegramAdapter(token="test_token")
            await adapter.connect()

            await adapter.send_typing_indicator("12345")

            mock_bot.send_chat_action.assert_called_once_with(
                chat_id="12345",
                action="typing",
            )
