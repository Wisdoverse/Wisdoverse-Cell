"""Tests for Google Chat adapter."""
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock the google api modules before importing the adapter
mock_googleapiclient = MagicMock()
mock_google_oauth2 = MagicMock()
sys.modules["googleapiclient"] = mock_googleapiclient
sys.modules["googleapiclient.discovery"] = mock_googleapiclient.discovery
sys.modules["google"] = MagicMock()
sys.modules["google.oauth2"] = mock_google_oauth2
sys.modules["google.oauth2.service_account"] = mock_google_oauth2.service_account

from shared.messaging.outbound.adapters._stable.google_chat import GoogleChatAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import OutboundMessage


class TestGoogleChatAdapterAttributes:
    def test_channel_id(self):
        adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
        assert adapter.channel_id == "google_chat"

    def test_channel_name(self):
        adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
        assert adapter.channel_name == "Google Chat"

    def test_status_is_stable(self):
        adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
        assert adapter.status == ChannelStatus.STABLE

    def test_capabilities_present(self):
        adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
        assert ChannelCapability.TEXT in adapter.capabilities
        assert ChannelCapability.RICH_MEDIA in adapter.capabilities
        assert ChannelCapability.EDIT_MESSAGE in adapter.capabilities
        assert ChannelCapability.DELETE_MESSAGE in adapter.capabilities
        assert ChannelCapability.GROUP_MANAGEMENT in adapter.capabilities
        assert ChannelCapability.WEBHOOKS in adapter.capabilities

    def test_capabilities_not_present(self):
        adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
        assert ChannelCapability.REACTIONS not in adapter.capabilities
        assert ChannelCapability.READ_RECEIPTS not in adapter.capabilities
        assert ChannelCapability.TYPING_INDICATOR not in adapter.capabilities


class TestGoogleChatAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_initializes_client(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.google_chat.build"
        ) as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
            await adapter.connect()

            mock_build.assert_called_once()
            assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.google_chat.build"
        ) as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
            await adapter.connect()
            await adapter.disconnect()

            assert adapter._client is None


class TestGoogleChatAdapterSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.google_chat.build"
        ) as mock_build:
            mock_service = MagicMock()
            mock_spaces = MagicMock()
            mock_messages = MagicMock()
            mock_create = MagicMock()

            mock_service.spaces.return_value = mock_spaces
            mock_spaces.messages.return_value = mock_messages
            mock_messages.create.return_value = mock_create
            mock_create.execute.return_value = {"name": "spaces/123/messages/456"}
            mock_build.return_value = mock_service

            adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
            await adapter.connect()

            message = OutboundMessage(
                channel_id="google_chat",
                target_chat_id="spaces/123",
                content="Hello Google Chat",
            )

            result = await adapter.send_message(message)

            assert result.success is True
            assert result.platform_message_id == "spaces/123/messages/456"

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
        message = OutboundMessage(
            channel_id="google_chat",
            target_chat_id="spaces/123",
            content="Hello",
        )
        result = await adapter.send_message(message)
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"


class TestGoogleChatAdapterEditDelete:
    @pytest.mark.asyncio
    async def test_edit_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.google_chat.build"
        ) as mock_build:
            mock_service = MagicMock()
            mock_spaces = MagicMock()
            mock_messages = MagicMock()
            mock_update = MagicMock()

            mock_service.spaces.return_value = mock_spaces
            mock_spaces.messages.return_value = mock_messages
            mock_messages.update.return_value = mock_update
            mock_update.execute.return_value = {"name": "spaces/123/messages/456"}
            mock_build.return_value = mock_service

            adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
            await adapter.connect()

            result = await adapter.edit_message(
                "spaces/123/messages/456", "Updated content"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.google_chat.build"
        ) as mock_build:
            mock_service = MagicMock()
            mock_spaces = MagicMock()
            mock_messages = MagicMock()
            mock_delete = MagicMock()

            mock_service.spaces.return_value = mock_spaces
            mock_spaces.messages.return_value = mock_messages
            mock_messages.delete.return_value = mock_delete
            mock_delete.execute.return_value = {}
            mock_build.return_value = mock_service

            adapter = GoogleChatAdapter(credentials_path="/path/to/creds.json")
            await adapter.connect()

            result = await adapter.delete_message("spaces/123/messages/456")

            assert result is True
