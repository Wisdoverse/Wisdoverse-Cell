"""User interaction API dependency wiring."""

from ..core.daily_progress_queries import DailyProgressQueryService
from ..db.daily_progress_store import SqlAlchemyDailyProgressQueryStore
from ..db.database import db_manager


def get_daily_progress_query_service() -> DailyProgressQueryService:
    return DailyProgressQueryService(SqlAlchemyDailyProgressQueryStore(db_manager))
