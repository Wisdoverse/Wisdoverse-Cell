"""Ports for Requirement Manager readiness checks."""

from typing import Protocol


class RequirementHealthStore(Protocol):
    """Readiness-check port for Requirement persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the Requirement database is reachable."""
