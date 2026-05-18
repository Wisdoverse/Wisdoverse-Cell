"""Application use cases for Analysis readiness checks."""
from __future__ import annotations

from typing import Any

from .health_ports import AnalysisHealthStore


class AnalysisHealthUseCase:
    """Build Analysis readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        health_store: AnalysisHealthStore,
        event_bus: Any,
    ) -> None:
        self._health_store = health_store
        self._event_bus = event_bus

    async def check(self) -> dict[str, bool]:
        return {
            "database": await self._health_store.is_database_ready(),
            "event_bus": self._event_bus is not None,
        }
