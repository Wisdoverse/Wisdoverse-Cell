"""Application use cases for PJM readiness checks."""
from __future__ import annotations

from typing import Any

from .health_ports import PJMHealthStore


class PJMHealthUseCase:
    """Build PJM readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        health_store: PJMHealthStore,
        config: Any,
    ) -> None:
        self._health_store = health_store
        self._config = config

    async def check(self) -> dict[str, bool]:
        return {
            "database": await self._health_store.is_database_ready(),
            "config_loaded": self._config_has_members(),
        }

    def _config_has_members(self) -> bool:
        if self._config is None:
            return False
        return len(getattr(self._config, "members", [])) > 0
