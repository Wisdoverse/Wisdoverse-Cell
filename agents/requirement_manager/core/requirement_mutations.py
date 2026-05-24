"""Application use cases for requirement mutation workflows."""

from shared.core.identifiers import RequirementId

from .requirement_mutation_workflow import (
    RequirementMutationSideEffectPublisher,
    RequirementMutationWorkflow,
)
from .unit_of_work_ports import RequirementUnitOfWorkFactory


class RequirementMutationUseCase:
    """Application use case for requirement update and delete operations."""

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

    async def update_requirement(
        self,
        *,
        requirement_id: str,
        changes: dict,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._mutation_workflow.update_requirement(
                requirement_id=RequirementId(requirement_id),
                changes=changes,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._side_effects.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def delete_requirement(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._mutation_workflow.delete_requirement(
                requirement_id=RequirementId(requirement_id),
                deleted_by=deleted_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._side_effects.publish_requirement_mutation_side_effects(result)
        return result.entity
