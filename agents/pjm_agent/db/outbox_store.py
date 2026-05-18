"""SQLAlchemy adapter for PJM event outbox persistence."""

from shared.schemas.event import Event

from ..core.outbox_ports import PJMEventOutboxStore
from .database import DatabaseManager
from .repository import PJMEventOutboxRepository


class SqlAlchemyPJMEventOutboxStore(PJMEventOutboxStore):
    """SQLAlchemy-backed PJM event outbox store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def add(self, event: Event) -> None:
        async with self._db_manager.session() as session:
            await self.stage(session, event)

    async def stage(self, session: object, event: Event) -> None:
        outbox = PJMEventOutboxRepository(session)
        await outbox.add(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        async with self._db_manager.session() as session:
            outbox = PJMEventOutboxRepository(session)
            return await outbox.list_pending(limit=limit)

    async def mark_published(self, event_id: str) -> None:
        async with self._db_manager.session() as session:
            outbox = PJMEventOutboxRepository(session)
            await outbox.mark_published(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        async with self._db_manager.session() as session:
            outbox = PJMEventOutboxRepository(session)
            await outbox.mark_failed(event_id, error)
