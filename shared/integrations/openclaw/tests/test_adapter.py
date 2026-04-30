"""
Tests for OpenClawChannelAdapter (MessageChannel interface)

Tests:
1. channel_name returns "openclaw"
2. send_message sends text via RPC
3. send_card converts and sends card via RPC
4. update_card sends update via RPC
5. handle_callback returns success
"""
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
from shared.integrations.openclaw.adapter import OpenClawChannelAdapter
from shared.integrations.openclaw.client import OpenClawClient


@pytest.fixture
def mock_client() -> OpenClawClient:
    client = OpenClawClient.__new__(OpenClawClient)
    client._connected = True
    client.send_request = AsyncMock(return_value={})
    return client


@pytest.fixture
def adapter(mock_client: OpenClawClient) -> OpenClawChannelAdapter:
    return OpenClawChannelAdapter(mock_client)


class TestChannelName:
    def test_channel_name(self, adapter: OpenClawChannelAdapter) -> None:
        assert adapter.channel_name == "openclaw"

    def test_is_message_channel(self, adapter: OpenClawChannelAdapter) -> None:
        assert isinstance(adapter, MessageChannel)


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_text(self, adapter: OpenClawChannelAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"message_id": "sent_001"}
        )
        content = ChannelMessage(content="Hello!", message_type="text")

        msg_id = await adapter.send_message("user_123", content)

        assert msg_id == "sent_001"
        adapter._client.send_request.assert_called_once_with(
            "channel.sendText",
            params={
                "chat_id": "user_123",
                "text": "Hello!",
                "format": "text",
            },
        )

    @pytest.mark.asyncio
    async def test_send_markdown(self, adapter: OpenClawChannelAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"message_id": "sent_002"}
        )
        content = ChannelMessage(content="**bold**", message_type="markdown")

        msg_id = await adapter.send_message("user_123", content)

        assert msg_id == "sent_002"
        call_params = adapter._client.send_request.call_args[1]["params"]
        assert call_params["format"] == "markdown"


class TestSendCard:
    @pytest.mark.asyncio
    async def test_send_card(self, adapter: OpenClawChannelAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"message_id": "sent_003"}
        )
        card = ChannelCard(
            card_id="card_001",
            title="Test Card",
            elements=[
                CardElement(element_type="text", content="Hello"),
                CardElement(element_type="divider"),
                CardElement(
                    element_type="field",
                    fields=[{"label": "Status", "value": "Open"}],
                ),
            ],
            actions=[
                CardAction(action_id="approve", label="Approve", style="primary"),
            ],
        )

        msg_id = await adapter.send_card("user_123", card)

        assert msg_id == "sent_003"
        call_args = adapter._client.send_request.call_args
        params = call_args[1]["params"]
        openclaw_card = params["card"]
        assert openclaw_card["card_id"] == "card_001"
        assert openclaw_card["title"] == "Test Card"
        assert len(openclaw_card["elements"]) == 3
        assert openclaw_card["elements"][0] == {"type": "text", "content": "Hello"}
        assert openclaw_card["elements"][1] == {"type": "divider"}
        assert len(openclaw_card["actions"]) == 1
        assert openclaw_card["actions"][0]["action_id"] == "approve"


class TestUpdateCard:
    @pytest.mark.asyncio
    async def test_update_card_success(
        self, adapter: OpenClawChannelAdapter
    ) -> None:
        adapter._client.send_request = AsyncMock(return_value={"success": True})
        card = ChannelCard(
            card_id="card_001",
            title="Updated",
            elements=[],
            actions=[],
        )

        result = await adapter.update_card("msg_001", card)

        assert result is True

    @pytest.mark.asyncio
    async def test_update_card_failure(
        self, adapter: OpenClawChannelAdapter
    ) -> None:
        adapter._client.send_request = AsyncMock(return_value={"success": False})
        card = ChannelCard(
            card_id="card_001",
            title="Updated",
            elements=[],
            actions=[],
        )

        result = await adapter.update_card("msg_001", card)

        assert result is False


class TestHandleCallback:
    @pytest.mark.asyncio
    async def test_handle_callback(self, adapter: OpenClawChannelAdapter) -> None:
        result = await adapter.handle_callback({"action": "test"})

        assert isinstance(result, ChannelResponse)
        assert result.success is True
