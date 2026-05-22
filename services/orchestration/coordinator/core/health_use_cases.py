"""Application use cases for Coordinator readiness checks."""
from __future__ import annotations

from typing import Any

from .health_ports import CoordinatorHealthStore


class CoordinatorHealthUseCase:
    """Build Coordinator readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        scratchpad: Any,
        state_store: Any,
        llm_gateway: Any,
        database_enabled: bool,
        health_store: CoordinatorHealthStore | None,
    ) -> None:
        self._scratchpad = scratchpad
        self._state_store = state_store
        self._llm_gateway = llm_gateway
        self._database_enabled = database_enabled
        self._health_store = health_store

    async def check(self) -> dict[str, bool]:
        checks = {
            "scratchpad": self._scratchpad.is_initialized(),
            "state_store": self._state_store is not None,
            "llm_gateway": self._llm_gateway is not None,
        }
        if self._database_enabled:
            checks["database"] = False
            if self._health_store is None:
                raise RuntimeError("coordinator_database_not_started")
            checks["database"] = await self._health_store.is_database_ready()
        return checks
