"""Ports for Requirement aggregate persistence."""

from typing import Any, Protocol

from shared.core.identifiers import RequirementId


class RequirementStore(Protocol):
    """Persistence port for requirement application use cases."""

    async def create_batch(self, requirements: list[Any]) -> list[Any]:
        """Create requirements in a batch."""

    async def get_by_id(self, requirement_id: RequirementId) -> Any | None:
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

    async def update(self, requirement_id: RequirementId, **kwargs: Any) -> Any | None:
        """Update one requirement."""

    async def confirm(
        self,
        requirement_id: RequirementId,
        confirmed_by: str,
    ) -> Any | None:
        """Confirm one requirement."""

    async def reject(
        self,
        requirement_id: RequirementId,
        reason: str,
        rejected_by: str,
    ) -> Any | None:
        """Reject one requirement."""

    async def delete(self, requirement_id: RequirementId) -> Any | None:
        """Delete one requirement."""
