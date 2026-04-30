# shared/integrations/wecom/tests/test_adapter.py
"""Tests for WeCom MessageChannel adapter."""
from unittest.mock import AsyncMock

import pytest

from shared.integrations.channels import (
    CardAction,
    CardElement,
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    MessageChannel,
)
from shared.integrations.wecom.adapter import WecomChannelAdapter


class TestWecomChannelAdapter:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.send_text_message = AsyncMock(return_value="msg_123")
        client.send_template_card = AsyncMock(return_value="msg_456")
        client.update_template_card = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def adapter(self, mock_client):
        return WecomChannelAdapter(client=mock_client)

    def test_implements_message_channel(self, adapter):
        assert isinstance(adapter, MessageChannel)

    def test_channel_name(self, adapter):
        assert adapter.channel_name == "wecom"

    @pytest.mark.asyncio
    async def test_send_message(self, adapter, mock_client):
        msg = ChannelMessage(content="Hello")
        result = await adapter.send_message("user1", msg)
        assert result == "msg_123"
        mock_client.send_text_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_card(self, adapter, mock_client):
        card = ChannelCard(
            card_id="req_1",
            title="Test",
            elements=[CardElement(element_type="text", content="Desc")],
            actions=[CardAction(action_id="confirm", label="Confirm", style="primary")]
        )
        result = await adapter.send_card("user1", card)
        assert result == "msg_456"
        mock_client.send_template_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback(self, adapter):
        result = await adapter.handle_callback({"action": "test"})
        assert isinstance(result, ChannelResponse)
        assert result.success is True
