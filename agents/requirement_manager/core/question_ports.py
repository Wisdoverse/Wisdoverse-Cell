"""Ports for Requirement clarification-question persistence."""

from typing import Any, Protocol


class RequirementQuestionStore(Protocol):
    """Persistence port for clarification-question use cases."""

    async def create_batch(self, questions: list[Any]) -> list[Any]:
        """Create clarification questions in a batch."""

    async def answer(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
    ) -> Any | None:
        """Answer one clarification question."""

    async def list_open(self, *, limit: int = 50) -> list[Any]:
        """Return unanswered clarification questions."""
