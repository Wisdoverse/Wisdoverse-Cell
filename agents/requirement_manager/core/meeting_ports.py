"""Ports for Requirement meeting persistence."""

from typing import Any, Protocol


class RequirementMeetingStore(Protocol):
    """Persistence port for meeting records used by requirement ingestion."""

    async def create(self, meeting: Any) -> Any:
        """Create one meeting record."""

    async def get_by_id(self, meeting_id: str) -> Any | None:
        """Return one meeting by id."""

    async def get_by_source_id(self, source: str, source_id: str) -> Any | None:
        """Return one meeting by source-system identity."""

    async def mark_processed(self, meeting_id: str) -> None:
        """Mark a meeting as processed."""
