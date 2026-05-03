"""Event handlers for channel gateway agent."""
from typing import TYPE_CHECKING

from shared.messaging.outbound.models.events import (
    ChannelEventTypes,
    MessageDeliveredPayload,
    MessageOutboundPayload,
)
from shared.messaging.outbound.models.messages import DeliveryResult, OutboundMessage
from shared.schemas.event import Event
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from services.gateways.channel.service.agent import ChannelGatewayAgent

logger = get_logger(__name__)

SUBSCRIBED_EVENTS = [
    ChannelEventTypes.MESSAGE_OUTBOUND,
]


async def dispatch_event(agent: "ChannelGatewayAgent", event: Event) -> list[Event]:
    """Route events to appropriate handlers."""
    handlers = {
        ChannelEventTypes.MESSAGE_OUTBOUND: handle_message_outbound,
    }

    handler = handlers.get(event.event_type)
    if handler is None:
        logger.warning("unhandled_event_type", event_type=event.event_type)
        return []

    logger.info(
        "handling_event",
        event_type=event.event_type,
        trace_id=event.metadata.trace_id if event.metadata else None,
    )

    try:
        return await handler(agent, event)
    except Exception as e:
        logger.error("event_handler_failed", event_type=event.event_type, error=str(e))
        raise


async def handle_message_outbound(
    agent: "ChannelGatewayAgent", event: Event
) -> list[Event]:
    """Handle outbound message request."""
    payload = MessageOutboundPayload.model_validate(event.payload)
    message = payload.message
    trace_id = _resolve_trace_id(event, message)

    logger.info(
        "processing_outbound_message",
        message_id=message.message_id,
        channel_id=message.channel_id,
        trace_id=trace_id,
    )

    adapter = agent._adapter_registry.get(message.channel_id)
    if adapter is None:
        result = DeliveryResult(
            success=False,
            error_code="adapter_not_found",
            error_message=f"No adapter registered for channel '{message.channel_id}'",
        )
        return [_delivery_event(agent, message, result, trace_id)]

    try:
        result = await adapter.send_message(message)
    except Exception as exc:
        logger.error(
            "outbound_message_delivery_failed",
            message_id=message.message_id,
            channel_id=message.channel_id,
            error=str(exc),
        )
        result = DeliveryResult(
            success=False,
            error_code=exc.__class__.__name__,
            error_message=str(exc),
        )

    return [_delivery_event(agent, message, result, trace_id)]


def _resolve_trace_id(event: Event, message: OutboundMessage) -> str | None:
    if event.metadata and event.metadata.trace_id:
        return event.metadata.trace_id
    return message.trace_id


def _delivery_event(
    agent: "ChannelGatewayAgent",
    message: OutboundMessage,
    result: DeliveryResult,
    trace_id: str | None,
) -> Event:
    payload = MessageDeliveredPayload(
        message_id=message.message_id,
        channel_id=message.channel_id,
        result=result,
    )
    return agent.create_event(
        event_type=ChannelEventTypes.MESSAGE_DELIVERED,
        payload=payload.model_dump(mode="json"),
        trace_id=trace_id,
    )
