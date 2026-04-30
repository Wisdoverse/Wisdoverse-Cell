"""Event handlers for channel gateway agent."""
from typing import TYPE_CHECKING

from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.schemas.event import Event
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from shared.messaging.outbound.service.agent import ChannelGatewayAgent

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
    logger.info("processing_outbound_message", payload=event.payload)

    # TODO: Implement message routing to adapters
    # 1. Extract OutboundMessage from payload
    # 2. Get adapter from registry
    # 3. Send message via adapter
    # 4. Return delivery result event

    return []
