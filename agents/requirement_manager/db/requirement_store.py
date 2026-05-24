"""SQLAlchemy adapter for Requirement aggregate persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import RequirementId

from ..core.requirement_ports import RequirementStore
from ..models import Requirement
from .repository import RequirementRepository


class SqlAlchemyRequirementStore(RequirementStore):
    """SQLAlchemy-backed requirement store."""

    def __init__(self, session: AsyncSession):
        self._requirements = RequirementRepository(session)

    async def create_batch(self, requirements: list):
        rows = [
            requirement
            if isinstance(requirement, Requirement)
            else Requirement(
                **(
                    requirement.requirement_kwargs()
                    if hasattr(requirement, "requirement_kwargs")
                    else dict(requirement)
                )
            )
            for requirement in requirements
        ]
        return await self._requirements.create_batch(rows)

    async def get_by_id(self, requirement_id: RequirementId):
        return await self._requirements.get_by_id(requirement_id)

    async def list_all(
        self,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ):
        return await self._requirements.list_all(
            status=status,
            category=category,
            priority=priority,
            skip=skip,
            limit=limit,
        )

    async def update(self, requirement_id: RequirementId, **kwargs):
        return await self._requirements.update(requirement_id, **kwargs)

    async def confirm(self, requirement_id: RequirementId, confirmed_by: str):
        return await self._requirements.confirm(requirement_id, confirmed_by)

    async def reject(
        self,
        requirement_id: RequirementId,
        reason: str,
        rejected_by: str,
    ):
        return await self._requirements.reject(
            requirement_id,
            reason=reason,
            rejected_by=rejected_by,
        )

    async def delete(self, requirement_id: RequirementId):
        return await self._requirements.delete(requirement_id)
