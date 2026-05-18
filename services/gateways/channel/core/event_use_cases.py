"""Application use cases for channel gateway event orchestration."""
from __future__ import annotations

from typing import Protocol

from shared.messaging.outbound.models.events import (
    ChannelEventTypes,
    MessageDeliveredPayload,
    MessageOutboundPayload,
)
from shared.messaging.outbound.models.messages import DeliveryResult, OutboundMessage
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger("channel_gateway.event_use_cases")

SUBSCRIBED_EVENTS = [
    ChannelEventTypes.MESSAGE_OUTBOUND,
]


class ChannelAdapterPort(Protocol):
    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send a message through the channel adapter."""


class ChannelAdapterRegistryPort(Protocol):
    def get(self, channel_id: str) -> ChannelAdapterPort | None:
        """Return the adapter registered for a channel."""


class ChannelGatewayEventUseCase:
    """Handle channel gateway domain events without service-private coupling."""

    def __init__(
        self,
        *,
        adapter_registry: ChannelAdapterRegistryPort,
        source_agent: str,
    ) -> None:
        self._adapter_registry = adapter_registry
        self._source_agent = source_agent

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type == ChannelEventTypes.MESSAGE_OUTBOUND:
            return await self._handle_message_outbound(event)

        logger.warning("unhandled_event_type", event_type=event.event_type)
        return []

    async def _handle_message_outbound(self, event: Event) -> list[Event]:
        payload = MessageOutboundPayload.model_validate(event.payload)
        message = payload.message
        trace_id = self._resolve_trace_id(event, message)

        logger.info(
            "processing_outbound_message",
            message_hash=hash_identifier(message.message_id),
            channel_id=message.channel_id,
            trace_id=trace_id,
        )

        adapter = self._adapter_registry.get(message.channel_id)
        if adapter is None:
            result = DeliveryResult(
                success=False,
                error_code="adapter_not_found",
                error_message=f"No adapter registered for channel '{message.channel_id}'",
            )
            return [self._delivery_event(message, result, trace_id)]

        try:
            result = await adapter.send_message(message)
        except Exception as exc:
            logger.error(
                "outbound_message_delivery_failed",
                message_hash=hash_identifier(message.message_id),
                channel_id=message.channel_id,
                error=str(exc),
            )
            result = DeliveryResult(
                success=False,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )

        return [self._delivery_event(message, result, trace_id)]

    @staticmethod
    def _resolve_trace_id(event: Event, message: OutboundMessage) -> str | None:
        if event.metadata and event.metadata.trace_id:
            return event.metadata.trace_id
        return message.trace_id

    def _delivery_event(
        self,
        message: OutboundMessage,
        result: DeliveryResult,
        trace_id: str | None,
    ) -> Event:
        payload = MessageDeliveredPayload(
            message_id=message.message_id,
            channel_id=message.channel_id,
            result=result,
        )
        return Event.create(
            event_type=ChannelEventTypes.MESSAGE_DELIVERED,
            source_agent=self._source_agent,
            payload=payload.model_dump(mode="json"),
            trace_id=trace_id,
        )
