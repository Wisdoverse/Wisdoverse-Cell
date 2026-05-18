"""SQLAlchemy adapter for Coordinator readiness checks."""

from sqlalchemy import text

from shared.utils.logger import get_logger

from ..core.health_ports import CoordinatorHealthStore
from .database import DatabaseManager

logger = get_logger("coordinator.health_store")


class SqlAlchemyCoordinatorHealthStore(CoordinatorHealthStore):
    """SQLAlchemy-backed Coordinator database health check."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def is_database_ready(self) -> bool:
        try:
            async with self._db_manager.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error(
                "coordinator_health_check_db_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False
