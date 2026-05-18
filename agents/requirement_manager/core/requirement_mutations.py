"""Application use cases for requirement mutation workflows."""

from typing import Protocol


class RequirementMutationAgent(Protocol):
    async def update_requirement(
        self,
        requirement_id: str,
        changes: dict,
        session: object,
    ) -> object | None:
        """Update one requirement."""

    async def delete_requirement(
        self,
        requirement_id: str,
        deleted_by: str,
        session: object,
    ) -> object | None:
        """Delete one requirement."""


class RequirementMutationUseCase:
    """Application use case for requirement update and delete operations."""

    def __init__(self, *, agent: RequirementMutationAgent, session: object):
        self._agent = agent
        self._session = session

    async def update_requirement(
        self,
        *,
        requirement_id: str,
        changes: dict,
    ) -> object | None:
        return await self._agent.update_requirement(
            requirement_id=requirement_id,
            changes=changes,
            session=self._session,
        )

    async def delete_requirement(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
    ) -> object | None:
        return await self._agent.delete_requirement(
            requirement_id=requirement_id,
            deleted_by=deleted_by,
            session=self._session,
        )
