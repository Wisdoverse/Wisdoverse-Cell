"""Application use cases for Requirement Manager readiness checks."""
from __future__ import annotations

from typing import Any, Protocol

from .health_ports import RequirementHealthStore


class RequirementEventBusHealthPort(Protocol):
    """Event bus readiness boundary for Requirement Manager health checks."""

    is_connected: bool


class RequirementHealthUseCase:
    """Build Requirement Manager readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        health_store: RequirementHealthStore,
        event_bus: RequirementEventBusHealthPort,
        messenger: Any,
        card_renderer: Any,
    ) -> None:
        self._health_store = health_store
        self._event_bus = event_bus
        self._messenger = messenger
        self._card_renderer = card_renderer

    async def check(self) -> dict[str, bool]:
        return {
            "database": await self._health_store.is_database_ready(),
            "event_bus": bool(getattr(self._event_bus, "is_connected", False)),
            "messenger": self._messenger is not None,
            "card_renderer": self._card_renderer is not None,
        }
