# shared/integrations/channels/tests/test_base.py
"""Tests for MessageChannel base class."""
import pytest

from shared.integrations.channels.base import MessageChannel
from shared.integrations.channels.types import (
    CardAction,
    CardElement,
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
)


class MockChannel(MessageChannel):
    """Mock implementation for testing."""

    def __init__(self):
        self._sent_messages = []
        self._sent_cards = []

    @property
    def channel_name(self) -> str:
        return "mock"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        self._sent_messages.append((user_id, content))
        return "msg_123"

    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        self._sent_cards.append((user_id, card))
        return "msg_456"

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        return True

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        return ChannelResponse(success=True)


class TestMessageChannel:
    def test_channel_name(self):
        channel = MockChannel()
        assert channel.channel_name == "mock"

    @pytest.mark.asyncio
    async def test_send_message(self):
        channel = MockChannel()
        msg = ChannelMessage(content="Hello")
        result = await channel.send_message("user_1", msg)
        assert result == "msg_123"
        assert len(channel._sent_messages) == 1

    @pytest.mark.asyncio
    async def test_send_card(self):
        channel = MockChannel()
        card = ChannelCard(
            card_id="card_1",
            title="Test",
            elements=[CardElement(element_type="text", content="Hello")],
            actions=[CardAction(action_id="ok", label="OK")]
        )
        result = await channel.send_card("user_1", card)
        assert result == "msg_456"
        assert len(channel._sent_cards) == 1

    @pytest.mark.asyncio
    async def test_update_card(self):
        channel = MockChannel()
        card = ChannelCard(
            card_id="card_1",
            title="Updated",
            elements=[CardElement(element_type="text", content="Updated content")],
            actions=[CardAction(action_id="ok", label="OK")]
        )
        result = await channel.update_card("msg_123", card)
        assert result is True

    @pytest.mark.asyncio
    async def test_handle_callback(self):
        channel = MockChannel()
        result = await channel.handle_callback({"action": "test"})
        assert result.success is True


class TestMessageChannelAbstract:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            MessageChannel()
