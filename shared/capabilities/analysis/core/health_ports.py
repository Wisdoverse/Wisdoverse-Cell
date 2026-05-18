"""Ports for Analysis capability readiness checks."""

from typing import Protocol


class AnalysisHealthStore(Protocol):
    """Readiness-check port for Analysis persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the Analysis database is reachable."""
