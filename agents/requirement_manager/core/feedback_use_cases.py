"""Application use cases for requirement feedback workflows."""

from dataclasses import dataclass
from typing import Any, Protocol

from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class BatchOperationSummary:
    """Summary for batch requirement feedback operations."""

    total: int
    succeeded: int
    failed: int
    results: list[dict]


class RequirementFeedbackAgent(Protocol):
    async def confirm_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> Any:
        """Confirm one requirement."""

    async def reject_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> Any:
        """Reject one requirement."""

    async def answer_question_with_uow(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork,
    ) -> Any:
        """Answer one open question."""

    async def batch_confirm_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[Any]]:
        """Confirm multiple requirements."""

    async def batch_reject_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[Any]]:
        """Reject multiple requirements."""

    async def publish_requirement_mutation_side_effects(self, result: Any) -> None:
        """Publish post-commit mutation side effects."""


class RequirementFeedbackUseCase:
    """Application use case for requirement feedback operations."""

    def __init__(
        self,
        *,
        agent: RequirementFeedbackAgent,
        uow_factory: RequirementUnitOfWorkFactory,
    ):
        self._agent = agent
        self._uow_factory = uow_factory

    async def confirm_requirement(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._agent.confirm_requirement_with_uow(
                requirement_id=requirement_id,
                confirmed_by=confirmed_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._agent.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def reject_requirement(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._agent.reject_requirement_with_uow(
                requirement_id=requirement_id,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._agent.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def answer_question(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._agent.answer_question_with_uow(
                question_id,
                answer=answer,
                answered_by=answered_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        return result.entity

    async def list_open_questions(self) -> list[object]:
        async with self._uow_factory() as uow:
            return await uow.questions.list_open()

    async def batch_confirm_requirements(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
    ) -> BatchOperationSummary:
        async with self._uow_factory() as uow:
            results, mutation_results = await self._agent.batch_confirm_requirements_with_uow(
                requirement_ids=requirement_ids,
                confirmed_by=confirmed_by,
                uow=uow,
            )
            await uow.commit()

        for result in mutation_results:
            await self._agent.publish_requirement_mutation_side_effects(result)
        return _summarize_batch(results)

    async def batch_reject_requirements(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> BatchOperationSummary:
        async with self._uow_factory() as uow:
            results, mutation_results = await self._agent.batch_reject_requirements_with_uow(
                requirement_ids=requirement_ids,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
            await uow.commit()

        for result in mutation_results:
            await self._agent.publish_requirement_mutation_side_effects(result)
        return _summarize_batch(results)


def _summarize_batch(results: list[dict]) -> BatchOperationSummary:
    succeeded = sum(1 for result in results if result["success"])
    failed = len(results) - succeeded
    return BatchOperationSummary(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )
