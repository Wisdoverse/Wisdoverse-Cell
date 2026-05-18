"""Outbound event publishing port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from shared.schemas.event import Event


class EventPublisher(Protocol):
    """Outbound port for publishing integration events."""

    async def publish(self, event: Event) -> bool:
        """Publish an event and return whether delivery was accepted."""
