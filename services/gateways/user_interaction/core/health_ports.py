"""Ports for User Interaction Gateway readiness checks."""

from typing import Protocol


class UserInteractionHealthStore(Protocol):
    """Readiness-check port for User Interaction persistence dependencies."""

    async def is_database_ready(self) -> bool:
        """Return whether the User Interaction database is reachable."""
