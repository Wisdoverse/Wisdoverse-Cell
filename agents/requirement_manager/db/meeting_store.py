"""SQLAlchemy adapter for Requirement meeting persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import MeetingId

from ..core.meeting_ports import RequirementMeetingStore
from ..models import Meeting
from .repository import MeetingRepository


class SqlAlchemyRequirementMeetingStore(RequirementMeetingStore):
    """SQLAlchemy-backed meeting store."""

    def __init__(self, session: AsyncSession):
        self._meetings = MeetingRepository(session)

    async def create(self, meeting):
        if isinstance(meeting, Meeting):
            row = meeting
        elif hasattr(meeting, "meeting_kwargs"):
            row = Meeting(**meeting.meeting_kwargs())
        else:
            row = Meeting(**dict(meeting))
        return await self._meetings.create(row)

    async def get_by_id(self, meeting_id: MeetingId):
        return await self._meetings.get_by_id(meeting_id)

    async def get_by_source_id(self, source: str, source_id: str):
        return await self._meetings.get_by_source_id(source, source_id)

    async def mark_processed(self, meeting_id: MeetingId) -> None:
        await self._meetings.mark_processed(meeting_id)
