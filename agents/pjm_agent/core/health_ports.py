"""Ports for PJM Agent readiness checks."""

from typing import Protocol


class PJMHealthStore(Protocol):
    """Readiness-check port for PJM persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the PJM database is reachable."""
