"""Ports for Requirement feedback-learning persistence."""

from typing import Any, Protocol


class RequirementFeedbackStore(Protocol):
    """Persistence port for feedback-learning records."""

    async def create(self, feedback: Any) -> Any:
        """Create one feedback record."""

    async def get_examples_for_prompt(self, limit: int = 5) -> list[dict]:
        """Return feedback examples formatted for prompt construction."""

    async def count_by_type(self) -> dict[str, int]:
        """Count feedback records by feedback type."""

    async def list_recent(
        self,
        limit: int = 20,
        feedback_type: str | None = None,
        unused_only: bool = False,
    ) -> list[Any]:
        """Return recent feedback records."""
