"""Application use cases for Sync readiness checks."""
from __future__ import annotations

from .health_ports import SyncHealthStore


class SyncHealthUseCase:
    """Build Sync readiness responses outside the service shell."""

    def __init__(self, *, health_store: SyncHealthStore) -> None:
        self._health_store = health_store

    async def check(self) -> dict[str, bool]:
        return {"database": await self._health_store.is_database_ready()}
