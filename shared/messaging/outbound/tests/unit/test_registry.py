"""Tests for adapter registry."""
from typing import AsyncIterator

from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import ChannelCapability, ChannelStatus
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    OutboundMessage,
)


class FakeAdapter(BaseChannelAdapter):
    channel_id = "fake"
    channel_name = "Fake"
    status = ChannelStatus.STABLE
    capabilities = {ChannelCapability.TEXT}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        return DeliveryResult(success=True)

    async def listen(self) -> AsyncIterator[InboundMessage]:
        return
        yield


class TestAdapterRegistry:
    def setup_method(self):
        self.registry = AdapterRegistry()

    def test_register_adapter(self):
        adapter = FakeAdapter()
        self.registry.register(adapter)
        assert self.registry.has("fake")

    def test_get_adapter(self):
        adapter = FakeAdapter()
        self.registry.register(adapter)
        retrieved = self.registry.get("fake")
        assert retrieved is adapter

    def test_get_nonexistent_adapter(self):
        result = self.registry.get("nonexistent")
        assert result is None

    def test_unregister_adapter(self):
        adapter = FakeAdapter()
        self.registry.register(adapter)
        self.registry.unregister("fake")
        assert not self.registry.has("fake")

    def test_list_adapters(self):
        adapter = FakeAdapter()
        self.registry.register(adapter)
        adapters = self.registry.list_all()
        assert len(adapters) == 1
        assert adapters[0] is adapter

    def test_list_by_status(self):
        adapter = FakeAdapter()
        self.registry.register(adapter)
        stable = self.registry.list_by_status(ChannelStatus.STABLE)
        experimental = self.registry.list_by_status(ChannelStatus.EXPERIMENTAL)
        assert len(stable) == 1
        assert len(experimental) == 0

    def test_has_adapter(self):
        adapter = FakeAdapter()
        self.registry.register(adapter)
        assert self.registry.has("fake") is True
        assert self.registry.has("nonexistent") is False
