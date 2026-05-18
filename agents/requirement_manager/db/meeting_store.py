"""SQLAlchemy adapter for Requirement meeting persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.meeting_ports import RequirementMeetingStore
from .repository import MeetingRepository


class SqlAlchemyRequirementMeetingStore(RequirementMeetingStore):
    """SQLAlchemy-backed meeting store."""

    def __init__(self, session: AsyncSession):
        self._meetings = MeetingRepository(session)

    async def create(self, meeting):
        return await self._meetings.create(meeting)

    async def get_by_id(self, meeting_id: str):
        return await self._meetings.get_by_id(meeting_id)

    async def mark_processed(self, meeting_id: str) -> None:
        await self._meetings.mark_processed(meeting_id)
