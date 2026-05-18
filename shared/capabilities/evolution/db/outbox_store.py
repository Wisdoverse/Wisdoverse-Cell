"""SQLAlchemy adapter for Evolution event outbox persistence."""

from shared.evolution.db.database import EvolutionDatabaseManager
from shared.evolution.db.repository import EvolutionEventOutboxRepository
from shared.schemas.event import Event

from ..core.outbox_ports import EvolutionEventOutboxStore


class SqlAlchemyEvolutionEventOutboxStore(EvolutionEventOutboxStore):
    """SQLAlchemy-backed Evolution event outbox store."""

    def __init__(self, db_manager: EvolutionDatabaseManager):
        self._db_manager = db_manager

    async def add(self, event: Event) -> None:
        async with self._db_manager.session() as session:
            outbox = EvolutionEventOutboxRepository(session)
            await outbox.add(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        async with self._db_manager.session() as session:
            outbox = EvolutionEventOutboxRepository(session)
            return await outbox.list_pending(limit=limit)

    async def mark_published(self, event_id: str) -> None:
        async with self._db_manager.session() as session:
            outbox = EvolutionEventOutboxRepository(session)
            await outbox.mark_published(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        async with self._db_manager.session() as session:
            outbox = EvolutionEventOutboxRepository(session)
            await outbox.mark_failed(event_id, error)
