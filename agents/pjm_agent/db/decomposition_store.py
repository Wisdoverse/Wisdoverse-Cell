"""SQLAlchemy adapter for PJM decomposition persistence."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from shared.schemas.event import Event

from ..core.decomposition_ports import PJMDecompositionStore, PJMDecompositionTransaction
from .database import DatabaseManager
from .repository import DecompositionRepository, PJMEventOutboxRepository


class _SqlAlchemyPJMDecompositionTransaction(PJMDecompositionTransaction):
    """SQLAlchemy-backed transaction-scoped decomposition operations."""

    def __init__(self, session):
        self._decompositions = DecompositionRepository(session)
        self._outbox = PJMEventOutboxRepository(session)

    async def create(
        self,
        wp_id: int,
        project_id: int,
        decompose_result: dict,
        assignee_id: int | None = None,
    ):
        return await self._decompositions.create(
            wp_id=wp_id,
            project_id=project_id,
            decompose_result=decompose_result,
            assignee_id=assignee_id,
        )

    async def get_by_wp_id(self, wp_id: int):
        return await self._decompositions.get_by_wp_id(wp_id)

    async def update_status(
        self,
        wp_id: int,
        status: str,
        approved_by: str | None = None,
    ) -> bool:
        return await self._decompositions.update_status(
            wp_id=wp_id,
            status=status,
            approved_by=approved_by,
        )

    async def delete_by_wp_id(self, wp_id: int) -> bool:
        return await self._decompositions.delete_by_wp_id(wp_id)

    async def stage_event(self, event: Event) -> None:
        await self._outbox.add(event)


class SqlAlchemyPJMDecompositionStore(PJMDecompositionStore):
    """SQLAlchemy-backed decomposition workflow store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PJMDecompositionTransaction]:
        async with self._db_manager.session() as session:
            yield _SqlAlchemyPJMDecompositionTransaction(session)

    async def list_stale_pending(
        self,
        *,
        older_than_hours: int = 24,
    ):
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            return await repo.get_stale_pending(older_than_hours=older_than_hours)
