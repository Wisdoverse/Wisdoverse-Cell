"""Application use cases for channel gateway event orchestration."""
from __future__ import annotations

from shared.messaging.outbound.models.events import (
    ChannelEventTypes,
    MessageDeliveredPayload,
    MessageOutboundPayload,
)
from shared.messaging.outbound.models.messages import OutboundMessage
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .provider_acl import (
    ChannelProviderACL,
    ChannelProviderDeliveryRequest,
    ChannelProviderDeliveryResponse,
    ChannelProviderRegistryPort,
)

logger = get_logger("channel_gateway.event_use_cases")

SUBSCRIBED_EVENTS = [
    ChannelEventTypes.MESSAGE_OUTBOUND,
]


class ChannelGatewayEventUseCase:
    """Handle channel gateway domain events without service-private coupling."""

    def __init__(
        self,
        *,
        adapter_registry: ChannelProviderRegistryPort,
        source_agent: str,
        provider_acl: ChannelProviderACL | None = None,
    ) -> None:
        self._adapter_registry = adapter_registry
        self._source_agent = source_agent
        self._provider_acl = provider_acl or ChannelProviderACL()

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

        request = ChannelProviderDeliveryRequest(
            message=message,
            trace_id=trace_id,
        )
        adapter = self._adapter_registry.get(request.channel_id)
        if adapter is None:
            response = self._provider_acl.adapter_missing(request)
        else:
            response = await self._provider_acl.deliver(
                adapter=adapter,
                request=request,
            )

        if not response.result.success:
            logger.error(
                "outbound_message_delivery_failed",
                message_hash=hash_identifier(request.message_id),
                channel_id=request.channel_id,
                error_code=response.result.error_code,
            )

        return [self._delivery_event(response)]

    @staticmethod
    def _resolve_trace_id(event: Event, message: OutboundMessage) -> str | None:
        if event.metadata and event.metadata.trace_id:
            return event.metadata.trace_id
        return message.trace_id

    def _delivery_event(
        self,
        response: ChannelProviderDeliveryResponse,
    ) -> Event:
        request = response.request
        payload = MessageDeliveredPayload(
            message_id=request.message_id,
            channel_id=request.channel_id,
            result=response.result,
        )
        return Event.create(
            event_type=ChannelEventTypes.MESSAGE_DELIVERED,
            source_agent=self._source_agent,
            payload=payload.model_dump(mode="json"),
            trace_id=request.trace_id,
        )
