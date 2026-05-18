"""Ports for PJM event outbox persistence."""

from typing import Protocol

from shared.schemas.event import Event


class PJMEventOutboxStore(Protocol):
    """Persistence port for PJM integration-event outbox operations."""

    async def add(self, event: Event) -> None:
        """Stage an event before external publish."""

    async def stage(self, session: object, event: Event) -> None:
        """Stage an event inside an existing local transaction."""

    async def list_pending(self, limit: int = 100) -> list[object]:
        """Return pending outbox rows."""

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure."""
