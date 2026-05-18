"""SQLAlchemy adapter for Dev event outbox persistence."""

from shared.schemas.event import Event

from ..core.outbox_ports import DevEventOutboxStore
from .database import DatabaseManager
from .repository import DevEventOutboxRepository


class SqlAlchemyDevEventOutboxStore(DevEventOutboxStore):
    """SQLAlchemy-backed Dev event outbox store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def add(self, event: Event) -> None:
        async with self._db_manager.session() as session:
            outbox = DevEventOutboxRepository(session)
            await outbox.add(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        async with self._db_manager.session() as session:
            outbox = DevEventOutboxRepository(session)
            return await outbox.list_pending(limit=limit)

    async def mark_published(self, event_id: str) -> None:
        async with self._db_manager.session() as session:
            outbox = DevEventOutboxRepository(session)
            await outbox.mark_published(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        async with self._db_manager.session() as session:
            outbox = DevEventOutboxRepository(session)
            await outbox.mark_failed(event_id, error)


class SqlAlchemyDevEventOutboxSessionStore(DevEventOutboxStore):
    """Session-scoped Dev event outbox store for local transactions."""

    def __init__(self, session):
        self._outbox = DevEventOutboxRepository(session)

    async def add(self, event: Event) -> None:
        await self._outbox.add(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        return await self._outbox.list_pending(limit=limit)

    async def mark_published(self, event_id: str) -> None:
        await self._outbox.mark_published(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        await self._outbox.mark_failed(event_id, error)
