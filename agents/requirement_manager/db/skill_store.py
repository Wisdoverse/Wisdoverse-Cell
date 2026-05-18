"""SQLAlchemy adapter for Requirement Manager business skills."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.skill_ports import RequirementSkillStore
from .repository import MeetingRepository, RequirementRepository


class SqlAlchemyRequirementSkillStore(RequirementSkillStore):
    """Repository-backed store for chat-triggered requirement skills."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._requirements = RequirementRepository(session)
        self._meetings = MeetingRepository(session)

    async def get_by_id(self, requirement_id: str):
        return await self._requirements.get_by_id(requirement_id)

    async def list_all(
        self,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ):
        return await self._requirements.list_all(
            status=status,
            skip=skip,
            limit=limit,
        )

    async def confirm(self, requirement_id: str, confirmed_by: str):
        return await self._requirements.confirm(requirement_id, confirmed_by)

    async def reject(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
    ):
        return await self._requirements.reject(
            requirement_id,
            reason=reason,
            rejected_by=rejected_by,
        )

    async def commit(self) -> None:
        await self._session.commit()

    async def count_by_status(self):
        return await self._requirements.count_by_status()

    async def count_by_priority(self):
        return await self._requirements.count_by_priority()

    async def count_by_category(self):
        return await self._requirements.count_by_category()

    async def get_daily_counts(self, *, days: int):
        return await self._requirements.get_daily_counts(days=days)

    async def count_today(self):
        return await self._requirements.count_today()

    async def meeting_counts(self) -> tuple[int, int]:
        _, total_meetings = await self._meetings.list_all(limit=1)
        unprocessed = await self._meetings.list_unprocessed(limit=1000)
        return total_meetings, len(unprocessed)


def build_requirement_skill_store(session: AsyncSession) -> RequirementSkillStore:
    """Build the default skill persistence adapter."""
    return SqlAlchemyRequirementSkillStore(session)
