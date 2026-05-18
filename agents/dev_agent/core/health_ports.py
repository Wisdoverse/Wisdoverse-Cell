"""Ports for Dev Agent readiness checks."""

from typing import Protocol


class DevHealthStore(Protocol):
    """Readiness-check port for Dev Agent persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the Dev Agent database is reachable."""
