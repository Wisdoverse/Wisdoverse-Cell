"""Application use cases for requirement feedback workflows."""

from dataclasses import dataclass

from .requirement_mutation_workflow import (
    RequirementMutationSideEffectPublisher,
    RequirementMutationWorkflow,
)
from .unit_of_work_ports import RequirementUnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class BatchOperationSummary:
    """Summary for batch requirement feedback operations."""

    total: int
    succeeded: int
    failed: int
    results: list[dict]


class RequirementFeedbackUseCase:
    """Application use case for requirement feedback operations."""

    def __init__(
        self,
        *,
        mutation_workflow: RequirementMutationWorkflow,
        side_effects: RequirementMutationSideEffectPublisher,
        uow_factory: RequirementUnitOfWorkFactory,
    ):
        self._mutation_workflow = mutation_workflow
        self._side_effects = side_effects
        self._uow_factory = uow_factory

    async def confirm_requirement(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._mutation_workflow.confirm_requirement(
                requirement_id=requirement_id,
                confirmed_by=confirmed_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._side_effects.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def reject_requirement(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._mutation_workflow.reject_requirement(
                requirement_id=requirement_id,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._side_effects.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def answer_question(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._mutation_workflow.answer_question(
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
            results, mutation_results = await self._mutation_workflow.batch_confirm_requirements(
                requirement_ids=requirement_ids,
                confirmed_by=confirmed_by,
                uow=uow,
            )
            await uow.commit()

        for result in mutation_results:
            await self._side_effects.publish_requirement_mutation_side_effects(result)
        return _summarize_batch(results)

    async def batch_reject_requirements(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> BatchOperationSummary:
        async with self._uow_factory() as uow:
            results, mutation_results = await self._mutation_workflow.batch_reject_requirements(
                requirement_ids=requirement_ids,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
            await uow.commit()

        for result in mutation_results:
            await self._side_effects.publish_requirement_mutation_side_effects(result)
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
