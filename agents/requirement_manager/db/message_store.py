"""SQLAlchemy adapter for Requirement chat-message persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.message_ports import RequirementMessageStore
from .repository import MessageRepository


class SqlAlchemyRequirementMessageStore(RequirementMessageStore):
    """SQLAlchemy-backed chat-message store."""

    def __init__(self, session: AsyncSession):
        self._messages = MessageRepository(session)

    async def create(self, message):
        return await self._messages.create(message)

    async def get_by_feishu_message_id(self, feishu_message_id: str):
        return await self._messages.get_by_feishu_message_id(feishu_message_id)

    async def get_by_session(self, session_id: str):
        return await self._messages.get_by_session(session_id)

    async def count_by_session(self, session_id: str) -> int:
        return await self._messages.count_by_session(session_id)

    async def mark_extracted(self, session_id: str, requirement_ids: list[str]) -> int:
        return await self._messages.mark_extracted(session_id, requirement_ids)
