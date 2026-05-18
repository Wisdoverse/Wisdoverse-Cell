"""SQLAlchemy persistence adapters for user-interaction chat."""

from .database import DatabaseManager
from .repository import ConversationRepository


class SqlAlchemyChatHistoryStore:
    """SQLAlchemy-backed implementation of the chat history store port."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def get_by_user(self, user_id: str) -> list[dict] | None:
        async with self._db_manager.session() as session:
            repo = ConversationRepository(session)
            return await repo.get_by_user(user_id)

    async def save(self, user_id: str, messages: list[dict]) -> None:
        async with self._db_manager.session() as session:
            repo = ConversationRepository(session)
            await repo.save(user_id, messages)

    async def clear(self, user_id: str) -> None:
        async with self._db_manager.session() as session:
            repo = ConversationRepository(session)
            await repo.clear(user_id)

    async def delete_inactive(self, days: int = 30) -> int:
        async with self._db_manager.session() as session:
            repo = ConversationRepository(session)
            deleted = await repo.delete_inactive(days=days)
            await session.commit()
            return deleted
