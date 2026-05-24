"""Ports for Requirement feedback-learning persistence."""

from typing import Any, Protocol

from shared.core.identifiers import FeedbackRecordId, RequirementId


class RequirementFeedbackStore(Protocol):
    """Persistence port for feedback-learning records."""

    async def create(self, feedback: Any) -> Any:
        """Create one feedback record."""

    async def get_by_id(self, feedback_id: FeedbackRecordId) -> Any | None:
        """Return one feedback record."""

    async def list_by_requirement(
        self,
        requirement_id: RequirementId,
    ) -> list[Any]:
        """Return feedback records for one requirement."""

    async def get_examples_for_prompt(self, limit: int = 5) -> list[dict]:
        """Return feedback examples formatted for prompt construction."""

    async def mark_used(self, feedback_ids: list[FeedbackRecordId]) -> int:
        """Mark feedback records as used in prompt construction."""

    async def count_by_type(self) -> dict[str, int]:
        """Count feedback records by feedback type."""

    async def list_recent(
        self,
        limit: int = 20,
        feedback_type: str | None = None,
        unused_only: bool = False,
    ) -> list[Any]:
        """Return recent feedback records."""
