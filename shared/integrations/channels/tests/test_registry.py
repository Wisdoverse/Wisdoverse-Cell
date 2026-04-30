# shared/integrations/channels/tests/test_registry.py
"""Tests for ChannelRegistry."""

from shared.integrations.channels.base import MessageChannel
from shared.integrations.channels.registry import ChannelRegistry
from shared.integrations.channels.types import (
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
)


class FakeChannel(MessageChannel):
    """Fake channel for testing."""

    def __init__(self, name: str):
        self._name = name

    @property
    def channel_name(self) -> str:
        return self._name

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        return "msg_1"

    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        return "msg_2"

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        return True

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        return ChannelResponse(success=True)


class TestChannelRegistry:
    def setup_method(self):
        """Reset registry before each test."""
        ChannelRegistry.clear()

    def test_register_and_get(self):
        channel = FakeChannel("test")
        ChannelRegistry.register(channel)

        result = ChannelRegistry.get("test")
        assert result is channel

    def test_get_nonexistent_returns_none(self):
        result = ChannelRegistry.get("nonexistent")
        assert result is None

    def test_register_multiple_channels(self):
        ch1 = FakeChannel("feishu")
        ch2 = FakeChannel("wecom")

        ChannelRegistry.register(ch1)
        ChannelRegistry.register(ch2)

        assert ChannelRegistry.get("feishu") is ch1
        assert ChannelRegistry.get("wecom") is ch2

    def test_all_returns_copy(self):
        ch1 = FakeChannel("feishu")
        ChannelRegistry.register(ch1)

        all_channels = ChannelRegistry.all()
        assert "feishu" in all_channels

        # Modifying returned dict doesn't affect registry
        all_channels["fake"] = FakeChannel("fake")
        assert ChannelRegistry.get("fake") is None

    def test_clear(self):
        ch1 = FakeChannel("test")
        ChannelRegistry.register(ch1)
        assert ChannelRegistry.get("test") is not None

        ChannelRegistry.clear()
        assert ChannelRegistry.get("test") is None

    def test_overwrite_existing_channel(self):
        ch1 = FakeChannel("test")
        ch2 = FakeChannel("test")

        ChannelRegistry.register(ch1)
        ChannelRegistry.register(ch2)

        assert ChannelRegistry.get("test") is ch2
