"""Ports for Requirement clarification-question persistence."""

from typing import Any, Protocol

from shared.core.identifiers import OpenQuestionId


class RequirementQuestionStore(Protocol):
    """Persistence port for clarification-question use cases."""

    async def create_batch(self, questions: list[Any]) -> list[Any]:
        """Create clarification questions in a batch."""

    async def answer(
        self,
        question_id: OpenQuestionId,
        *,
        answer: str,
        answered_by: str,
    ) -> Any | None:
        """Answer one clarification question."""

    async def list_open(self, *, limit: int = 50) -> list[Any]:
        """Return unanswered clarification questions."""
