"""SQLAlchemy adapter for chat-agent operation logs."""

from ..core.domain.card_operation import CardOperationLogEntry
from ..core.ops_logger import CardOperationLogStore
from .database import DatabaseManager
from .repository import CardOperationRepository


class SqlAlchemyCardOperationLogStore(CardOperationLogStore):
    """SQLAlchemy-backed card-operation log store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def record(
        self,
        *,
        entry: CardOperationLogEntry,
    ) -> None:
        async with self._db_manager.session() as session:
            repo = CardOperationRepository(session)
            await repo.record(entry)

    async def query(
        self,
        user_id: str = "",
        action: str = "",
        limit: int = 20,
    ) -> list[object]:
        async with self._db_manager.session() as session:
            repo = CardOperationRepository(session)
            return await repo.query(user_id=user_id, action=action, limit=limit)
