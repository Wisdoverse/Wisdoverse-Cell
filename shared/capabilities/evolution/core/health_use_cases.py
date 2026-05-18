"""Application use cases for Evolution readiness checks."""
from __future__ import annotations

from typing import Any, Protocol

from .health_ports import EvolutionHealthStore


class EvolutionEventBusHealthPort(Protocol):
    """Event bus readiness boundary for Evolution health checks."""

    is_connected: bool


class EvolutionHealthUseCase:
    """Build Evolution readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        health_store: EvolutionHealthStore,
        event_bus: EvolutionEventBusHealthPort,
        llm_gateway: Any,
        approval_service: Any,
        collaboration_enabled: bool,
        approval_gateway: Any,
    ) -> None:
        self._health_store = health_store
        self._event_bus = event_bus
        self._llm_gateway = llm_gateway
        self._approval_service = approval_service
        self._collaboration_enabled = collaboration_enabled
        self._approval_gateway = approval_gateway

    async def check(self) -> dict[str, bool]:
        checks = {
            "database": await self._health_store.is_database_ready(),
            "event_bus": bool(getattr(self._event_bus, "is_connected", False)),
            "llm_gateway": self._llm_gateway is not None,
            "control_plane_approval_service": self._approval_service is not None,
        }
        if self._collaboration_enabled:
            checks["collaboration_approval_gateway"] = (
                self._approval_gateway is not None
            )
        return checks
