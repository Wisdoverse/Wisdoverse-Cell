"""Tests for base channel adapter."""
from typing import AsyncIterator

import pytest

from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import ChannelCapability, ChannelStatus
from shared.messaging.outbound.core.exceptions import NotSupportedError
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    OutboundMessage,
)


class MockAdapter(BaseChannelAdapter):
    """Mock adapter for testing."""

    channel_id = "mock"
    channel_name = "Mock Channel"
    status = ChannelStatus.STABLE
    capabilities = {ChannelCapability.TEXT, ChannelCapability.RICH_MEDIA}

    def __init__(self):
        self._connected = False
        self._messages: list[InboundMessage] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        return DeliveryResult(success=True, platform_message_id="mock_123")

    async def listen(self) -> AsyncIterator[InboundMessage]:
        for msg in self._messages:
            yield msg


class TestBaseChannelAdapter:
    def test_mock_adapter_has_required_attributes(self):
        adapter = MockAdapter()
        assert adapter.channel_id == "mock"
        assert adapter.channel_name == "Mock Channel"
        assert adapter.status == ChannelStatus.STABLE
        assert ChannelCapability.TEXT in adapter.capabilities

    def test_has_capability(self):
        adapter = MockAdapter()
        assert adapter.has_capability(ChannelCapability.TEXT) is True
        assert adapter.has_capability(ChannelCapability.REACTIONS) is False

    @pytest.mark.asyncio
    async def test_connect(self):
        adapter = MockAdapter()
        await adapter.connect()
        assert adapter._connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        adapter = MockAdapter()
        adapter._connected = True
        await adapter.disconnect()
        assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_send_message(self):
        adapter = MockAdapter()
        msg = OutboundMessage(
            channel_id="mock",
            target_chat_id="chat1",
            content="Test",
        )
        result = await adapter.send_message(msg)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_edit_message_raises_not_supported(self):
        adapter = MockAdapter()
        with pytest.raises(NotSupportedError) as exc_info:
            await adapter.edit_message("msg1", "new content")
        assert "mock" in str(exc_info.value)
        assert "edit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_message_raises_not_supported(self):
        adapter = MockAdapter()
        with pytest.raises(NotSupportedError):
            await adapter.delete_message("msg1")

    @pytest.mark.asyncio
    async def test_add_reaction_raises_not_supported(self):
        adapter = MockAdapter()
        with pytest.raises(NotSupportedError):
            await adapter.add_reaction("msg1", "👍")

    @pytest.mark.asyncio
    async def test_send_typing_indicator_raises_not_supported(self):
        adapter = MockAdapter()
        with pytest.raises(NotSupportedError):
            await adapter.send_typing_indicator("chat1")

    @pytest.mark.asyncio
    async def test_mark_as_read_raises_not_supported(self):
        adapter = MockAdapter()
        with pytest.raises(NotSupportedError):
            await adapter.mark_as_read("msg1")
