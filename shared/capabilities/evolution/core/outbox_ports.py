"""Ports for evolution capability event outbox persistence."""

from typing import Protocol

from shared.schemas.event import Event


class EvolutionEventOutboxStore(Protocol):
    """Persistence port for Evolution integration-event outbox operations."""

    async def add(self, event: Event) -> None:
        """Stage an event before external publish."""

    async def list_pending(self, limit: int = 100) -> list[object]:
        """Return pending outbox rows."""

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure."""
