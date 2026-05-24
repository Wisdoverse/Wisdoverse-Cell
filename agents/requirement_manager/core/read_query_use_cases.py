"""Application query orchestration for Requirement agent-facing reads."""
from __future__ import annotations

from typing import Any

from shared.core.identifiers import MeetingId, RequirementId

from .agent_read_use_cases import RequirementAgentReadUseCase
from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory


class RequirementReadQueryUseCase:
    """Run Requirement read queries through an explicit persistence boundary."""

    def __init__(
        self,
        *,
        uow_factory: RequirementUnitOfWorkFactory,
    ) -> None:
        self._uow_factory = uow_factory

    async def list_pending_requirements(
        self,
        *,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict[str, Any]], int, int]:
        async with self._uow_factory() as uow:
            return await self.list_pending_requirements_with_uow(
                uow,
                page=page,
                page_size=page_size,
            )

    async def list_pending_requirements_with_uow(
        self,
        uow: RequirementUnitOfWork,
        *,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict[str, Any]], int, int]:
        return await self._read_model_for_uow(uow).list_pending_requirements(
            page=page,
            page_size=page_size,
        )

    async def get_confirmed_requirements(self) -> list[dict[str, Any]]:
        async with self._uow_factory() as uow:
            return await self.get_confirmed_requirements_with_uow(uow)

    async def get_confirmed_requirements_with_uow(
        self,
        uow: RequirementUnitOfWork,
    ) -> list[dict[str, Any]]:
        return await self._read_model_for_uow(uow).get_confirmed_requirements()

    async def get_requirement(self, requirement_id: str) -> Any | None:
        async with self._uow_factory() as uow:
            return await self.get_requirement_with_uow(uow, requirement_id)

    async def get_requirement_with_uow(
        self,
        uow: RequirementUnitOfWork,
        requirement_id: str,
    ) -> Any | None:
        return await self._read_model_for_uow(uow).get_requirement(RequirementId(requirement_id))

    async def get_meeting(self, meeting_id: str) -> Any | None:
        async with self._uow_factory() as uow:
            return await self.get_meeting_with_uow(uow, meeting_id)

    async def get_meeting_with_uow(
        self,
        uow: RequirementUnitOfWork,
        meeting_id: str,
    ) -> Any | None:
        return await self._read_model_for_uow(uow).get_meeting(MeetingId(meeting_id))

    async def list_open_questions(self, *, limit: int = 50) -> list[Any]:
        async with self._uow_factory() as uow:
            return await self.list_open_questions_with_uow(uow, limit=limit)

    async def list_open_questions_with_uow(
        self,
        uow: RequirementUnitOfWork,
        *,
        limit: int = 50,
    ) -> list[Any]:
        return await self._read_model_for_uow(uow).list_open_questions(limit=limit)

    def _read_model_for_uow(
        self,
        uow: RequirementUnitOfWork,
    ) -> RequirementAgentReadUseCase:
        return RequirementAgentReadUseCase(
            requirements=uow.requirements,
            meetings=uow.meetings,
            questions=uow.questions,
        )
