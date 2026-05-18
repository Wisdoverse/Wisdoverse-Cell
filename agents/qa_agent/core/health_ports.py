"""Ports for QA Agent readiness checks."""

from typing import Protocol


class QAHealthStore(Protocol):
    """Readiness-check port for QA persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the QA database is reachable."""
