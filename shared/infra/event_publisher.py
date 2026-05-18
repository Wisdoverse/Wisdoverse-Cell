"""Outbound event publishing adapters."""

from shared.core.event_publisher import EventPublisher
from shared.schemas.event import Event


class EventBusEventPublisher(EventPublisher):
    """EventPublisher adapter for existing EventBus implementations."""

    def __init__(self, event_bus):
        self._event_bus = event_bus

    async def publish(self, event: Event) -> bool:
        result = await self._event_bus.publish(event)
        return result is not False
