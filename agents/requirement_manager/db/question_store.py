"""SQLAlchemy adapter for Requirement clarification-question persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import OpenQuestionId

from ..core.question_ports import RequirementQuestionStore
from ..models import OpenQuestion
from .repository import QuestionRepository


class SqlAlchemyRequirementQuestionStore(RequirementQuestionStore):
    """SQLAlchemy-backed clarification-question store."""

    def __init__(self, session: AsyncSession):
        self._questions = QuestionRepository(session)

    async def create_batch(self, questions: list):
        rows = [
            question
            if isinstance(question, OpenQuestion)
            else OpenQuestion(
                **(
                    question.open_question_kwargs()
                    if hasattr(question, "open_question_kwargs")
                    else dict(question)
                )
            )
            for question in questions
        ]
        return await self._questions.create_batch(rows)

    async def answer(
        self,
        question_id: OpenQuestionId,
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
