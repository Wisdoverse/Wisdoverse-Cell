"""SQLAlchemy adapter for Evolution readiness checks."""

from sqlalchemy import text

from shared.evolution.db.database import EvolutionDatabaseManager
from shared.utils.logger import get_logger

from ..core.health_ports import EvolutionHealthStore

logger = get_logger("evolution_module.health_store")


class SqlAlchemyEvolutionHealthStore(EvolutionHealthStore):
    """SQLAlchemy-backed Evolution database health check."""

    def __init__(self, db_manager: EvolutionDatabaseManager):
        self._db_manager = db_manager

    async def is_database_ready(self) -> bool:
        try:
            async with self._db_manager.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error(
                "health_check_db_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False
