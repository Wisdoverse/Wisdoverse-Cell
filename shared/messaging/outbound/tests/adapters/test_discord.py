"""Tests for Discord adapter."""
import sys
from unittest.mock import AsyncMock, MagicMock

# Mock discord module before importing the adapter
mock_discord = MagicMock()
mock_discord.Client = MagicMock
mock_discord.Intents.default.return_value = MagicMock()
sys.modules["discord"] = mock_discord

from unittest.mock import patch

import pytest

from shared.messaging.outbound.adapters._stable.discord import DiscordAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import OutboundMessage


class TestDiscordAdapterAttributes:
    def test_channel_id(self):
        adapter = DiscordAdapter(token="test_token")
        assert adapter.channel_id == "discord"

    def test_channel_name(self):
        adapter = DiscordAdapter(token="test_token")
        assert adapter.channel_name == "Discord"

    def test_status_is_stable(self):
        adapter = DiscordAdapter(token="test_token")
        assert adapter.status == ChannelStatus.STABLE

    def test_capabilities(self):
        adapter = DiscordAdapter(token="test_token")
        assert ChannelCapability.TEXT in adapter.capabilities
        assert ChannelCapability.RICH_MEDIA in adapter.capabilities
        assert ChannelCapability.EDIT_MESSAGE in adapter.capabilities
        assert ChannelCapability.DELETE_MESSAGE in adapter.capabilities
        assert ChannelCapability.REACTIONS in adapter.capabilities
        assert ChannelCapability.TYPING_INDICATOR in adapter.capabilities
        # Discord does NOT support read receipts
        assert ChannelCapability.READ_RECEIPTS not in adapter.capabilities


class TestDiscordAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_initializes_client(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.discord.discord.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = DiscordAdapter(token="test_token")
            await adapter.connect()

            mock_client_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.discord.discord.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = DiscordAdapter(token="test_token")
            await adapter.connect()
            await adapter.disconnect()

            mock_client.close.assert_called_once()


class TestDiscordAdapterSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.discord.discord.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_channel = MagicMock()
            mock_message = MagicMock()
            mock_message.id = 123456789
            mock_channel.send = AsyncMock(return_value=mock_message)
            # get_channel is synchronous in discord.py
            mock_client.get_channel = MagicMock(return_value=mock_channel)
            mock_client_class.return_value = mock_client

            adapter = DiscordAdapter(token="test_token")
            await adapter.connect()

            message = OutboundMessage(
                channel_id="discord",
                target_chat_id="987654321",
                content="Hello Discord",
            )

            result = await adapter.send_message(message)

            assert result.success is True
            assert result.platform_message_id == "123456789"
            mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        adapter = DiscordAdapter(token="test_token")
        message = OutboundMessage(
            channel_id="discord",
            target_chat_id="987654321",
            content="Hello",
        )
        result = await adapter.send_message(message)
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"


class TestDiscordAdapterEditDelete:
    @pytest.mark.asyncio
    async def test_edit_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.discord.discord.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_channel = MagicMock()
            mock_message = MagicMock()
            mock_message.edit = AsyncMock()
            mock_channel.fetch_message = AsyncMock(return_value=mock_message)
            # get_channel is synchronous in discord.py
            mock_client.get_channel = MagicMock(return_value=mock_channel)
            mock_client_class.return_value = mock_client

            adapter = DiscordAdapter(token="test_token")
            adapter._channel_id_cache["123"] = "456"
            await adapter.connect()

            result = await adapter.edit_message("123", "New content")

            assert result is True
            mock_message.edit.assert_called_once_with(content="New content")

    @pytest.mark.asyncio
    async def test_delete_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.discord.discord.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_channel = MagicMock()
            mock_message = MagicMock()
            mock_message.delete = AsyncMock()
            mock_channel.fetch_message = AsyncMock(return_value=mock_message)
            # get_channel is synchronous in discord.py
            mock_client.get_channel = MagicMock(return_value=mock_channel)
            mock_client_class.return_value = mock_client

            adapter = DiscordAdapter(token="test_token")
            adapter._channel_id_cache["123"] = "456"
            await adapter.connect()

            result = await adapter.delete_message("123")

            assert result is True
            mock_message.delete.assert_called_once()


class TestDiscordAdapterTyping:
    @pytest.mark.asyncio
    async def test_send_typing_indicator(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.discord.discord.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_channel = MagicMock()
            mock_channel.typing = AsyncMock()
            mock_client.get_channel = MagicMock(return_value=mock_channel)
            mock_client_class.return_value = mock_client

            adapter = DiscordAdapter(token="test_token")
            await adapter.connect()

            await adapter.send_typing_indicator("123456789")

            mock_client.get_channel.assert_called_once_with(123456789)
            mock_channel.typing.assert_called_once()
