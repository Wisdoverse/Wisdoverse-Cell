"""Application read use cases exposed by the Requirement agent facade."""
from __future__ import annotations

from typing import Any

from shared.core.identifiers import MeetingId, RequirementId

from .meeting_ports import RequirementMeetingStore
from .question_ports import RequirementQuestionStore
from .requirement_ports import RequirementStore


class RequirementAgentReadUseCase:
    """Build Requirement agent-facing read projections outside the service shell."""

    def __init__(
        self,
        *,
        requirements: RequirementStore,
        meetings: RequirementMeetingStore,
        questions: RequirementQuestionStore,
    ) -> None:
        self._requirements = requirements
        self._meetings = meetings
        self._questions = questions

    async def list_pending_requirements(
        self,
        *,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict[str, Any]], int, int]:
        skip = (page - 1) * page_size
        requirements, total = await self._requirements.list_all(
            status="PENDING",
            skip=skip,
            limit=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        return [
            {
                "id": requirement.id,
                "title": requirement.title,
                "description": requirement.description,
                "priority": requirement.priority,
                "category": requirement.category,
            }
            for requirement in requirements
        ], total, total_pages

    async def get_confirmed_requirements(self) -> list[dict[str, Any]]:
        requirements, _ = await self._requirements.list_all(
            status="CONFIRMED",
            limit=1000,
        )
        return [
            {
                "id": requirement.id,
                "title": requirement.title,
                "description": requirement.description,
                "priority": requirement.priority,
                "category": requirement.category,
                "source_quote": requirement.source_quote,
                "status": requirement.status,
            }
            for requirement in requirements
        ]

    async def get_requirement(self, requirement_id: RequirementId) -> Any | None:
        return await self._requirements.get_by_id(requirement_id)

    async def get_meeting(self, meeting_id: MeetingId) -> Any | None:
        return await self._meetings.get_by_id(meeting_id)

    async def list_open_questions(self, *, limit: int = 50) -> list[Any]:
        return await self._questions.list_open(limit=limit)
