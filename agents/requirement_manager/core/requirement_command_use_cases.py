"""Application command use cases for Requirement mutations."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .requirement_mutation_workflow import (
    RequirementMutationResult,
    RequirementMutationSideEffectPublisher,
    RequirementMutationWorkflow,
)
from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory

MutationOperation = Callable[[RequirementUnitOfWork], Awaitable[RequirementMutationResult]]


class RequirementCommandUseCase:
    """Run Requirement mutation commands with explicit transaction boundaries."""

    def __init__(
        self,
        *,
        mutation_workflow: RequirementMutationWorkflow,
        side_effects: RequirementMutationSideEffectPublisher,
        uow_factory: RequirementUnitOfWorkFactory,
    ) -> None:
        self._mutation_workflow = mutation_workflow
        self._side_effects = side_effects
        self._uow_factory = uow_factory

    async def confirm_requirement(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        uow: RequirementUnitOfWork | None = None,
    ) -> Any | None:
        result = await self._run_mutation(
            lambda active_uow: self.confirm_requirement_with_uow(
                requirement_id=requirement_id,
                confirmed_by=confirmed_by,
                uow=active_uow,
            ),
            uow=uow,
            publish_side_effects=True,
        )
        return result.entity

    async def confirm_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._mutation_workflow.confirm_requirement(
            requirement_id=requirement_id,
            confirmed_by=confirmed_by,
            uow=uow,
        )

    async def reject_requirement(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork | None = None,
    ) -> Any | None:
        result = await self._run_mutation(
            lambda active_uow: self.reject_requirement_with_uow(
                requirement_id=requirement_id,
                reason=reason,
                rejected_by=rejected_by,
                uow=active_uow,
            ),
            uow=uow,
            publish_side_effects=True,
        )
        return result.entity

    async def reject_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._mutation_workflow.reject_requirement(
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by,
            uow=uow,
        )

    async def update_requirement(
        self,
        *,
        requirement_id: str,
        changes: dict[str, Any],
        uow: RequirementUnitOfWork | None = None,
    ) -> Any | None:
        result = await self._run_mutation(
            lambda active_uow: self.update_requirement_with_uow(
                requirement_id=requirement_id,
                changes=changes,
                uow=active_uow,
            ),
            uow=uow,
            publish_side_effects=True,
        )
        return result.entity

    async def update_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        changes: dict[str, Any],
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._mutation_workflow.update_requirement(
            requirement_id=requirement_id,
            changes=changes,
            uow=uow,
        )

    async def delete_requirement(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
        uow: RequirementUnitOfWork | None = None,
    ) -> Any | None:
        result = await self._run_mutation(
            lambda active_uow: self.delete_requirement_with_uow(
                requirement_id=requirement_id,
                deleted_by=deleted_by,
                uow=active_uow,
            ),
            uow=uow,
            publish_side_effects=True,
        )
        return result.entity

    async def delete_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._mutation_workflow.delete_requirement(
            requirement_id=requirement_id,
            deleted_by=deleted_by,
            uow=uow,
        )

    async def answer_question(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork | None = None,
    ) -> Any | None:
        result = await self._run_mutation(
            lambda active_uow: self.answer_question_with_uow(
                question_id,
                answer=answer,
                answered_by=answered_by,
                uow=active_uow,
            ),
            uow=uow,
            publish_side_effects=False,
        )
        return result.entity

    async def answer_question_with_uow(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        return await self._mutation_workflow.answer_question(
            question_id,
            answer=answer,
            answered_by=answered_by,
            uow=uow,
        )

    async def batch_confirm_requirements(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
        uow: RequirementUnitOfWork | None = None,
    ) -> list[dict]:
        results, mutation_results = await self._run_batch(
            lambda active_uow: self.batch_confirm_requirements_with_uow(
                requirement_ids=requirement_ids,
                confirmed_by=confirmed_by,
                uow=active_uow,
            ),
            uow=uow,
        )
        for result in mutation_results:
            await self._side_effects.publish_requirement_mutation_side_effects(result)
        return results

    async def batch_confirm_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        return await self._mutation_workflow.batch_confirm_requirements(
            requirement_ids=requirement_ids,
            confirmed_by=confirmed_by,
            uow=uow,
        )

    async def batch_reject_requirements(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork | None = None,
    ) -> list[dict]:
        results, mutation_results = await self._run_batch(
            lambda active_uow: self.batch_reject_requirements_with_uow(
                requirement_ids=requirement_ids,
                reason=reason,
                rejected_by=rejected_by,
                uow=active_uow,
            ),
            uow=uow,
        )
        for result in mutation_results:
            await self._side_effects.publish_requirement_mutation_side_effects(result)
        return results

    async def batch_reject_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        return await self._mutation_workflow.batch_reject_requirements(
            requirement_ids=requirement_ids,
            reason=reason,
            rejected_by=rejected_by,
            uow=uow,
        )

    async def _run_mutation(
        self,
        operation: MutationOperation,
        *,
        uow: RequirementUnitOfWork | None,
        publish_side_effects: bool,
    ) -> RequirementMutationResult:
        if uow is not None:
            result = await operation(uow)
            await uow.commit()
        else:
            async with self._uow_factory() as active_uow:
                result = await operation(active_uow)
                await active_uow.commit()

        if publish_side_effects:
            await self._side_effects.publish_requirement_mutation_side_effects(result)
        return result

    async def _run_batch(
        self,
        operation: Callable[
            [RequirementUnitOfWork],
            Awaitable[tuple[list[dict], list[RequirementMutationResult]]],
        ],
        *,
        uow: RequirementUnitOfWork | None,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        if uow is not None:
            results, mutation_results = await operation(uow)
            await uow.commit()
            return results, mutation_results

        async with self._uow_factory() as active_uow:
            results, mutation_results = await operation(active_uow)
            await active_uow.commit()
            return results, mutation_results
