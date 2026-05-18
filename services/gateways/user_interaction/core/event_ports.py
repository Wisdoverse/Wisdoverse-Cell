from typing import Protocol

from shared.schemas.event import Event


class GatewayEventPublisherPort(Protocol):
    """Port for publishing gateway-owned integration events."""

    async def publish_sync_trigger(self, *, scope: str) -> bool:
        """Publish a sync trigger command through the gateway boundary."""
        ...


class UserInteractionEventOutboxStore(Protocol):
    """Persistence port for user-interaction integration-event outbox operations."""

    async def add(self, event: Event) -> None:
        """Stage an event before external publish."""

    async def list_pending(self, limit: int = 100) -> list[object]:
        """Return pending outbox rows."""

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure."""
