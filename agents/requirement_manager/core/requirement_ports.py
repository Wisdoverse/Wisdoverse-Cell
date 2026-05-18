"""Ports for Requirement aggregate persistence."""

from typing import Any, Protocol


class RequirementStore(Protocol):
    """Persistence port for requirement application use cases."""

    async def create_batch(self, requirements: list[Any]) -> list[Any]:
        """Create requirements in a batch."""

    async def get_by_id(self, requirement_id: str) -> Any | None:
        """Return one requirement by id."""

    async def list_all(
        self,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Any], int]:
        """Return a filtered page of requirements."""

    async def update(self, requirement_id: str, **kwargs: Any) -> Any | None:
        """Update one requirement."""

    async def confirm(self, requirement_id: str, confirmed_by: str) -> Any | None:
        """Confirm one requirement."""

    async def reject(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
    ) -> Any | None:
        """Reject one requirement."""

    async def delete(self, requirement_id: str) -> Any | None:
        """Delete one requirement."""
