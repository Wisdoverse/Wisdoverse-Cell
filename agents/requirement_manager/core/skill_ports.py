"""Ports used by Requirement Manager business skills."""

from typing import Any, Protocol


class RequirementSkillStore(Protocol):
    """Persistence port for chat-triggered requirement skills."""

    async def get_by_id(self, requirement_id: str) -> Any | None:
        """Return one requirement by id."""

    async def list_all(
        self,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Any], int]:
        """Return a filtered page of requirements."""

    async def confirm(self, requirement_id: str, confirmed_by: str) -> Any | None:
        """Confirm one requirement and commit the write."""

    async def reject(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
    ) -> Any | None:
        """Reject one requirement and commit the write."""

    async def commit(self) -> None:
        """Commit pending skill writes."""

    async def count_by_status(self) -> dict[str, int]:
        """Return requirement counts by status."""

    async def count_by_priority(self) -> dict[str, int]:
        """Return requirement counts by priority."""

    async def count_by_category(self) -> dict[str, int]:
        """Return requirement counts by category."""

    async def get_daily_counts(self, *, days: int) -> list[dict[str, Any]]:
        """Return daily requirement counts."""

    async def count_today(self) -> int:
        """Return today's requirement count."""

    async def meeting_counts(self) -> tuple[int, int]:
        """Return total and unprocessed meeting counts."""
