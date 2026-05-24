"""Ports for Control Plane integration-event outbox persistence."""

from __future__ import annotations

from typing import Protocol

from shared.schemas.event import Event


class ControlPlaneEventOutboxStore(Protocol):
    """Persistence port for Control Plane integration-event outbox operations."""

    async def add(self, event: Event) -> None:
        """Stage an event before external publish."""

    async def list_pending(self, limit: int = 100) -> list[object]:
        """Return pending outbox rows."""

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure."""


__all__ = ["ControlPlaneEventOutboxStore"]
