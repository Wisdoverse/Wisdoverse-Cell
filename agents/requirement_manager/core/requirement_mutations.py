"""Application use cases for requirement mutation workflows."""

from typing import Any, Protocol

from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory


class RequirementMutationAgent(Protocol):
    async def update_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        changes: dict,
        uow: RequirementUnitOfWork,
    ) -> Any:
        """Update one requirement."""

    async def delete_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
        uow: RequirementUnitOfWork,
    ) -> Any:
        """Delete one requirement."""

    async def publish_requirement_mutation_side_effects(self, result: Any) -> None:
        """Publish post-commit mutation side effects."""


class RequirementMutationUseCase:
    """Application use case for requirement update and delete operations."""

    def __init__(
        self,
        *,
        agent: RequirementMutationAgent,
        uow_factory: RequirementUnitOfWorkFactory,
    ):
        self._agent = agent
        self._uow_factory = uow_factory

    async def update_requirement(
        self,
        *,
        requirement_id: str,
        changes: dict,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._agent.update_requirement_with_uow(
                requirement_id=requirement_id,
                changes=changes,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._agent.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def delete_requirement(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
    ) -> object | None:
        async with self._uow_factory() as uow:
            result = await self._agent.delete_requirement_with_uow(
                requirement_id=requirement_id,
                deleted_by=deleted_by,
                uow=uow,
            )
            if result.entity is None:
                return None
            await uow.commit()

        await self._agent.publish_requirement_mutation_side_effects(result)
        return result.entity
