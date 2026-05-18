"""SQLAlchemy adapter for Requirement clarification-question persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.question_ports import RequirementQuestionStore
from .repository import QuestionRepository


class SqlAlchemyRequirementQuestionStore(RequirementQuestionStore):
    """SQLAlchemy-backed clarification-question store."""

    def __init__(self, session: AsyncSession):
        self._questions = QuestionRepository(session)

    async def create_batch(self, questions: list):
        return await self._questions.create_batch(questions)

    async def answer(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
    ):
        return await self._questions.answer(
            question_id,
            answer=answer,
            answered_by=answered_by,
        )

    async def list_open(self, *, limit: int = 50):
        return await self._questions.list_open(limit=limit)
