"""Application use cases for QA readiness checks."""
from __future__ import annotations

from .health_ports import QAHealthStore


class QAHealthUseCase:
    """Build QA readiness responses outside the service shell."""

    def __init__(self, *, health_store: QAHealthStore) -> None:
        self._health_store = health_store

    async def check(self) -> dict[str, bool]:
        return {"database": await self._health_store.is_database_ready()}
