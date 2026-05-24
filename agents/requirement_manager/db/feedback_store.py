"""SQLAlchemy adapter for Requirement feedback-learning persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import FeedbackRecordId, RequirementId

from ..core.feedback_ports import RequirementFeedbackStore
from .repository import FeedbackRepository


class SqlAlchemyRequirementFeedbackStore(RequirementFeedbackStore):
    """SQLAlchemy-backed feedback-learning store."""

    def __init__(self, session: AsyncSession):
        self._feedback = FeedbackRepository(session)

    async def create(self, feedback):
        return await self._feedback.create(feedback)

    async def get_by_id(self, feedback_id: FeedbackRecordId):
        return await self._feedback.get_by_id(feedback_id)

    async def list_by_requirement(self, requirement_id: RequirementId):
        return await self._feedback.list_by_requirement(requirement_id)

    async def get_examples_for_prompt(self, limit: int = 5) -> list[dict]:
        return await self._feedback.get_examples_for_prompt(limit=limit)

    async def mark_used(self, feedback_ids: list[FeedbackRecordId]) -> int:
        return await self._feedback.mark_used(feedback_ids)

    async def count_by_type(self) -> dict[str, int]:
        return await self._feedback.count_by_type()

    async def list_recent(
        self,
        limit: int = 20,
        feedback_type: str | None = None,
        unused_only: bool = False,
    ):
        return await self._feedback.list_recent(
            limit=limit,
            feedback_type=feedback_type,
            unused_only=unused_only,
        )
