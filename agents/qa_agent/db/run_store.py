"""SQLAlchemy adapter for QA acceptance run persistence."""

from typing import Any

from ..core.run_store import QAAcceptanceRunRecord, QAAcceptanceRunStore
from ..models.schemas import QARunStats
from .database import DatabaseManager
from .repository import AcceptanceRunRepository


class SqlAlchemyQAAcceptanceRunStore(QAAcceptanceRunStore):
    """SQLAlchemy-backed QA acceptance run store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def get_by_id(self, run_id: str) -> QAAcceptanceRunRecord | None:
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            return await repo.get_by_id(run_id)

    async def get_by_trigger_event_id(
        self,
        trigger_event_id: str | None,
    ) -> QAAcceptanceRunRecord | None:
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            return await repo.get_by_trigger_event_id(trigger_event_id)

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[QAAcceptanceRunRecord]:
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            return await repo.list_runs(
                agent_name=agent_name,
                limit=limit,
                offset=offset,
            )

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            return await repo.get_stats(agent_name=agent_name, days=days)

    async def update_notification_summary(
        self,
        run_id: str,
        notification_summary: dict[str, Any],
    ) -> bool:
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            run = await repo.get_by_id(run_id)
            if run is None:
                return False
            run.notification_summary = notification_summary
            return True
