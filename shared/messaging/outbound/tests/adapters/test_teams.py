"""Tests for Microsoft Teams adapter."""
import sys
from unittest.mock import MagicMock

# Mock botbuilder modules before importing the adapter
mock_botbuilder_core = MagicMock()
mock_botbuilder_schema = MagicMock()

# Create mock classes
mock_botbuilder_core.BotFrameworkAdapter = MagicMock()
mock_botbuilder_core.BotFrameworkAdapterSettings = MagicMock()
mock_botbuilder_core.TurnContext = MagicMock()
mock_botbuilder_schema.Activity = MagicMock()
mock_botbuilder_schema.ActivityTypes = MagicMock()
mock_botbuilder_schema.ActivityTypes.message = "message"
mock_botbuilder_schema.ActivityTypes.typing = "typing"

sys.modules["botbuilder"] = MagicMock()
sys.modules["botbuilder.core"] = mock_botbuilder_core
sys.modules["botbuilder.schema"] = mock_botbuilder_schema

from unittest.mock import AsyncMock, patch

import pytest

from shared.messaging.outbound.adapters._stable.teams import TeamsAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import OutboundMessage


class TestTeamsAdapterAttributes:
    def test_channel_id(self):
        adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
        assert adapter.channel_id == "teams"

    def test_channel_name(self):
        adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
        assert adapter.channel_name == "Microsoft Teams"

    def test_status_is_stable(self):
        adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
        assert adapter.status == ChannelStatus.STABLE

    def test_capabilities(self):
        adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
        assert ChannelCapability.TEXT in adapter.capabilities
        assert ChannelCapability.RICH_MEDIA in adapter.capabilities
        assert ChannelCapability.EDIT_MESSAGE in adapter.capabilities
        assert ChannelCapability.DELETE_MESSAGE in adapter.capabilities
        assert ChannelCapability.REACTIONS in adapter.capabilities
        assert ChannelCapability.TYPING_INDICATOR in adapter.capabilities
        assert ChannelCapability.READ_RECEIPTS in adapter.capabilities
        assert ChannelCapability.GROUP_MANAGEMENT in adapter.capabilities
        assert ChannelCapability.WEBHOOKS in adapter.capabilities


class TestTeamsAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_initializes_adapter(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.teams.BotFrameworkAdapter"
        ) as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter

            adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
            await adapter.connect()

            mock_adapter_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.teams.BotFrameworkAdapter"
        ) as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter

            adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
            await adapter.connect()
            await adapter.disconnect()

            assert adapter._bot_adapter is None


class TestTeamsAdapterSendMessage:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.teams.BotFrameworkAdapter"
        ) as mock_adapter_class:
            mock_bot_adapter = MagicMock()
            mock_adapter_class.return_value = mock_bot_adapter

            # Create a mock TurnContext
            mock_turn_context = AsyncMock()
            mock_activity = MagicMock()
            mock_activity.id = "msg_123"
            mock_turn_context.send_activity.return_value = mock_activity

            adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
            await adapter.connect()

            # Store a turn context for the chat
            adapter._turn_contexts["12345"] = mock_turn_context

            message = OutboundMessage(
                channel_id="teams",
                target_chat_id="12345",
                content="Hello Teams",
            )

            result = await adapter.send_message(message)

            assert result.success is True
            assert result.platform_message_id == "msg_123"
            mock_turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
        message = OutboundMessage(
            channel_id="teams",
            target_chat_id="12345",
            content="Hello",
        )
        result = await adapter.send_message(message)
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"


class TestTeamsAdapterEditDelete:
    @pytest.mark.asyncio
    async def test_edit_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.teams.BotFrameworkAdapter"
        ) as mock_adapter_class:
            mock_bot_adapter = MagicMock()
            mock_adapter_class.return_value = mock_bot_adapter

            mock_turn_context = AsyncMock()

            adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
            adapter._activity_cache["msg_123"] = {
                "chat_id": "12345",
                "activity_id": "msg_123",
            }
            adapter._turn_contexts["12345"] = mock_turn_context
            await adapter.connect()

            result = await adapter.edit_message("msg_123", "New content")

            assert result is True
            mock_turn_context.update_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_message(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.teams.BotFrameworkAdapter"
        ) as mock_adapter_class:
            mock_bot_adapter = MagicMock()
            mock_adapter_class.return_value = mock_bot_adapter

            mock_turn_context = AsyncMock()

            adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
            adapter._activity_cache["msg_123"] = {
                "chat_id": "12345",
                "activity_id": "msg_123",
            }
            adapter._turn_contexts["12345"] = mock_turn_context
            await adapter.connect()

            result = await adapter.delete_message("msg_123")

            assert result is True
            mock_turn_context.delete_activity.assert_called_once()


class TestTeamsAdapterTyping:
    @pytest.mark.asyncio
    async def test_send_typing_indicator(self):
        with patch(
            "shared.messaging.outbound.adapters._stable.teams.BotFrameworkAdapter"
        ) as mock_adapter_class:
            mock_bot_adapter = MagicMock()
            mock_adapter_class.return_value = mock_bot_adapter

            mock_turn_context = AsyncMock()

            adapter = TeamsAdapter(app_id="test_app_id", app_password="test_password")
            adapter._turn_contexts["12345"] = mock_turn_context
            await adapter.connect()

            await adapter.send_typing_indicator("12345")

            mock_turn_context.send_activity.assert_called_once()
