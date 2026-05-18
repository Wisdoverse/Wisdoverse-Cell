"""Daily-progress persistence adapter for scheduled user-interaction jobs."""

from datetime import date
from typing import Any

from sqlalchemy import select

from ..core.daily_progress_queries import DailyProgressQueryRepository
from ..core.daily_tasks import DailyProgressItem, DailyProgressStore
from ..models.daily_progress import DailyProgress
from .database import DatabaseManager
from .repository import DailyProgressRepository


class SqlAlchemyDailyProgressStore(DailyProgressStore):
    """SQLAlchemy-backed implementation of the daily-progress store port."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def create_batch(self, items: list[dict[str, Any]]) -> None:
        async with self._db_manager.session() as session:
            repo = DailyProgressRepository(session)
            await repo.create_batch(items)

    async def list_users_for_date(self, target_date: Any) -> list[tuple[str, str]]:
        async with self._db_manager.session() as session:
            stmt = (
                select(DailyProgress.user_id, DailyProgress.user_name)
                .where(DailyProgress.date == target_date)
                .distinct()
            )
            result = await session.execute(stmt)
            return [(user_id, user_name) for user_id, user_name in result.all()]

    async def get_pending(
        self,
        user_id: str,
        target_date: Any,
    ) -> list[DailyProgressItem]:
        async with self._db_manager.session() as session:
            repo = DailyProgressRepository(session)
            return await repo.get_pending(user_id, target_date)

    async def update_progress(
        self,
        progress_id: int,
        status: str,
        raw_reply: str = "",
        note: str = "",
    ) -> object | None:
        async with self._db_manager.session() as session:
            repo = DailyProgressRepository(session)
            return await repo.update_progress(
                progress_id,
                status,
                raw_reply=raw_reply,
                note=note,
            )


class SqlAlchemyDailyProgressQueryStore(DailyProgressQueryRepository):
    """SQLAlchemy-backed daily-progress read-model query adapter."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def get_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str = "",
    ) -> list[object]:
        async with self._db_manager.session() as session:
            repo = DailyProgressRepository(session)
            return await repo.get_by_date_range(start_date, end_date, user_id=user_id)
