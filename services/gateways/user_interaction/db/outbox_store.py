"""SQLAlchemy adapter for user-interaction event outbox persistence."""

from shared.schemas.event import Event

from ..core.event_ports import UserInteractionEventOutboxStore
from .database import DatabaseManager
from .repository import UserInteractionEventOutboxRepository


class SqlAlchemyUserInteractionEventOutboxStore(UserInteractionEventOutboxStore):
    """SQLAlchemy-backed user-interaction event outbox store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def add(self, event: Event) -> None:
        async with self._db_manager.session() as session:
            outbox = UserInteractionEventOutboxRepository(session)
            await outbox.add(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        async with self._db_manager.session() as session:
            outbox = UserInteractionEventOutboxRepository(session)
            return await outbox.list_pending(limit=limit)

    async def mark_published(self, event_id: str) -> None:
        async with self._db_manager.session() as session:
            outbox = UserInteractionEventOutboxRepository(session)
            await outbox.mark_published(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        async with self._db_manager.session() as session:
            outbox = UserInteractionEventOutboxRepository(session)
            await outbox.mark_failed(event_id, error)
