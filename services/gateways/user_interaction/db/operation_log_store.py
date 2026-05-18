"""SQLAlchemy adapter for user-interaction operation logs."""

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
        user_id: str,
        user_name: str,
        action: str,
        result: str,
        table_id: str,
        record_id: str,
        assignee_name: str,
        fields_snapshot: str,
        error_message: str,
    ) -> None:
        async with self._db_manager.session() as session:
            repo = CardOperationRepository(session)
            await repo.record(
                user_id=user_id,
                user_name=user_name,
                action=action,
                result=result,
                table_id=table_id,
                record_id=record_id,
                assignee_name=assignee_name,
                fields_snapshot=fields_snapshot,
                error_message=error_message,
            )

    async def query(
        self,
        user_id: str = "",
        action: str = "",
        limit: int = 20,
    ) -> list[object]:
        async with self._db_manager.session() as session:
            repo = CardOperationRepository(session)
            return await repo.query(user_id=user_id, action=action, limit=limit)
