"""Ports for Sync capability readiness checks."""

from typing import Protocol


class SyncHealthStore(Protocol):
    """Readiness-check port for Sync persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the Sync database is reachable."""
