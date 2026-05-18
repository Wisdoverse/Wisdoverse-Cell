from unittest.mock import AsyncMock

import pytest

from services.gateways.channel.core.event_use_cases import ChannelGatewayEventUseCase
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    OutboundMessage,
)
from shared.schemas.event import Event


class _Registry:
    def __init__(self, adapter=None):
        self._adapter = adapter

    def get(self, channel_id: str):
        return self._adapter


def _event(message: OutboundMessage, trace_id: str | None = None) -> Event:
    return Event.create(
        event_type=ChannelEventTypes.MESSAGE_OUTBOUND,
        source_agent="test-agent",
        payload={"message": message.model_dump(mode="json")},
        trace_id=trace_id,
    )


@pytest.mark.asyncio
async def test_outbound_message_uses_registered_adapter_and_emits_delivery_event() -> None:
    adapter = AsyncMock()
    adapter.send_message = AsyncMock(
        return_value=DeliveryResult(
            success=True,
            platform_message_id="platform_msg_123",
        )
    )
    message = OutboundMessage(
        channel_id="fake",
        target_chat_id="chat_123",
        content="hello",
        trace_id="trc_message",
    )

    events = await ChannelGatewayEventUseCase(
        adapter_registry=_Registry(adapter),
        source_agent="channel-gateway",
    ).handle_event(_event(message, trace_id="trc_event"))

    adapter.send_message.assert_awaited_once_with(message)
    assert len(events) == 1
    delivered = events[0]
    assert delivered.event_type == ChannelEventTypes.MESSAGE_DELIVERED
    assert delivered.source_agent == "channel-gateway"
    assert delivered.metadata.trace_id == "trc_event"
    assert delivered.payload["message_id"] == message.message_id
    assert delivered.payload["channel_id"] == "fake"
    assert delivered.payload["result"]["success"] is True
    assert delivered.payload["result"]["platform_message_id"] == "platform_msg_123"


@pytest.mark.asyncio
async def test_missing_adapter_returns_failed_delivery_event_with_message_trace() -> None:
    message = OutboundMessage(
        channel_id="missing",
        target_chat_id="chat_123",
        content="hello",
        trace_id="trc_message",
    )

    events = await ChannelGatewayEventUseCase(
        adapter_registry=_Registry(),
        source_agent="channel-gateway",
    ).handle_event(_event(message))

    delivered = events[0]
    assert delivered.metadata.trace_id == "trc_message"
    assert delivered.payload["message_id"] == message.message_id
    assert delivered.payload["result"]["success"] is False
    assert delivered.payload["result"]["error_code"] == "adapter_not_found"


@pytest.mark.asyncio
async def test_adapter_exception_returns_failed_delivery_event() -> None:
    adapter = AsyncMock()
    adapter.send_message = AsyncMock(side_effect=RuntimeError("delivery failed"))
    message = OutboundMessage(
        channel_id="fake",
        target_chat_id="chat_123",
        content="hello",
    )

    events = await ChannelGatewayEventUseCase(
        adapter_registry=_Registry(adapter),
        source_agent="channel-gateway",
    ).handle_event(_event(message))

    delivered = events[0]
    assert delivered.payload["result"]["success"] is False
    assert delivered.payload["result"]["error_code"] == "RuntimeError"
    assert delivered.payload["result"]["error_message"] == "delivery failed"


@pytest.mark.asyncio
async def test_unhandled_event_type_returns_no_events() -> None:
    event = Event.create(
        event_type="unknown.event",
        source_agent="test-agent",
        payload={},
    )

    events = await ChannelGatewayEventUseCase(
        adapter_registry=_Registry(),
        source_agent="channel-gateway",
    ).handle_event(event)

    assert events == []
