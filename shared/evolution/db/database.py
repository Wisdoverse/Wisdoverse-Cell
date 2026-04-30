"""
EvolutionDatabaseManager — agent-specific subclass of BaseDatabaseManager.

Uses the shared evolution_metadata for table creation/migration.
"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_database import BaseDatabaseManager

from .tables import evolution_metadata


class EvolutionDatabaseManager(BaseDatabaseManager):
    def __init__(
        self,
        database_url: Optional[str] = None,
        read_database_url: Optional[str] = None,
    ):
        super().__init__(
            application_name="projectcell-evolution",
            metadata=evolution_metadata,
            database_url=database_url,
            read_database_url=read_database_url,
            logger_name="evolution.db",
        )


async def get_evolution_db(
    db_manager: EvolutionDatabaseManager,
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injection helper that yields a write session."""
    async with db_manager.session() as session:
        yield session
