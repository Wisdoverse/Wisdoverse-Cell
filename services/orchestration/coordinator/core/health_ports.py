"""Ports for Coordinator readiness checks."""

from typing import Protocol


class CoordinatorHealthStore(Protocol):
    """Readiness-check port for Coordinator persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the Coordinator database is reachable."""
