"""Application use cases for requirement export workflows."""

from collections.abc import Sequence
from typing import Protocol

from .generator import PRDGenerationResult, QuestionExportResult


class RequirementExportRepository(Protocol):
    async def list_all(
        self,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[object], int]:
        """Return requirements for export."""

    async def get_by_id(self, requirement_id: str) -> object | None:
        """Return one requirement by ID."""


class QuestionExportRepository(Protocol):
    async def list_open(self, limit: int = 50) -> Sequence[object]:
        """Return unanswered questions."""

    async def list_answered(self, limit: int = 50) -> Sequence[object]:
        """Return answered questions."""

    async def list_all(self, limit: int = 50) -> Sequence[object]:
        """Return all exportable questions."""


class DocumentExportGenerator(Protocol):
    async def generate_prd(
        self,
        requirements: list[dict],
        project_name: str = "Wisdoverse Cell",
        version: str = "1.0",
    ) -> PRDGenerationResult:
        """Generate a PRD document."""

    def generate_questions_export(
        self,
        questions: list[dict],
        project_name: str = "Wisdoverse Cell",
    ) -> QuestionExportResult:
        """Generate a question-list document."""


class ExportUseCase:
    """Application use case for PRD and question-list exports."""

    def __init__(
        self,
        requirement_repository: RequirementExportRepository,
        question_repository: QuestionExportRepository,
        generator: DocumentExportGenerator,
    ):
        self._requirements = requirement_repository
        self._questions = question_repository
        self._generator = generator

    async def export_prd(
        self,
        *,
        status: str | None = None,
        project_name: str = "Wisdoverse Cell",
        version: str = "1.0",
    ) -> PRDGenerationResult:
        requirements, _total = await self._requirements.list_all(
            status=status if status and status != "all" else None,
            limit=500,
        )
        return await self._generator.generate_prd(
            requirements=[
                {
                    "id": requirement.id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "category": requirement.category,
                    "priority": requirement.priority,
                    "status": requirement.status,
                    "source_quote": requirement.source_quote,
                    "confirmed_by": requirement.confirmed_by,
                    "confirmed_at": (
                        requirement.confirmed_at.isoformat()
                        if requirement.confirmed_at
                        else None
                    ),
                }
                for requirement in requirements
            ],
            project_name=project_name,
            version=version,
        )

    async def export_questions(
        self,
        *,
        status: str | None = None,
        project_name: str = "Wisdoverse Cell",
    ) -> QuestionExportResult:
        questions = await self._list_questions(status, limit=200)
        question_dicts = []
        for question in questions:
            requirement = await self._requirements.get_by_id(question.requirement_id)
            question_dicts.append(
                {
                    "id": question.id,
                    "question": question.question,
                    "context": question.context,
                    "status": question.status,
                    "answer": question.answer,
                    "answered_by": question.answered_by,
                    "requirement_title": (
                        requirement.title if requirement else "Unknown requirement"
                    ),
                }
            )

        return self._generator.generate_questions_export(
            questions=question_dicts,
            project_name=project_name,
        )

    async def _list_questions(
        self,
        status: str | None,
        *,
        limit: int,
    ) -> Sequence[object]:
        if status == "answered":
            return await self._questions.list_answered(limit=limit)
        if status == "all":
            return await self._questions.list_all(limit=limit)
        return await self._questions.list_open(limit=limit)
