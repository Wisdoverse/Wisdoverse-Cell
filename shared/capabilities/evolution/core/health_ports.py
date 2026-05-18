"""Ports for evolution capability readiness checks."""

from typing import Protocol


class EvolutionHealthStore(Protocol):
    """Readiness-check port for Evolution persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the Evolution database is reachable."""
