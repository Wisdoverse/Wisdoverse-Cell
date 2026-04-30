"""Tests for OpenClaw channel gateway adapter."""

from shared.messaging.outbound.adapters._stable.openclaw import OpenClawAdapter
from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)


class TestOpenClawAdapterMetadata:
    """Test adapter class attributes."""

    def test_channel_id(self) -> None:
        adapter = OpenClawAdapter(
            gateway_url="ws://localhost:18789",
            device_id="test",
            auth_token="test",
        )
        assert adapter.channel_id == "openclaw"

    def test_channel_name(self) -> None:
        adapter = OpenClawAdapter(
            gateway_url="ws://localhost:18789",
            device_id="test",
            auth_token="test",
        )
        assert adapter.channel_name == "OpenClaw"

    def test_status_is_stable(self) -> None:
        adapter = OpenClawAdapter(
            gateway_url="ws://localhost:18789",
            device_id="test",
            auth_token="test",
        )
        assert adapter.status == ChannelStatus.STABLE

    def test_has_text_capability(self) -> None:
        adapter = OpenClawAdapter(
            gateway_url="ws://localhost:18789",
            device_id="test",
            auth_token="test",
        )
        assert adapter.has_capability(ChannelCapability.TEXT)
        assert adapter.has_capability(ChannelCapability.RICH_MEDIA)
        assert adapter.has_capability(ChannelCapability.EDIT_MESSAGE)

    def test_is_base_channel_adapter(self) -> None:
        adapter = OpenClawAdapter(
            gateway_url="ws://localhost:18789",
            device_id="test",
            auth_token="test",
        )
        assert isinstance(adapter, BaseChannelAdapter)

    def test_is_subclass_of_base(self) -> None:
        assert issubclass(OpenClawAdapter, BaseChannelAdapter)
