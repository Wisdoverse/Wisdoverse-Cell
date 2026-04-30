"""Database Manager - qa_agent"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_database import BaseDatabaseManager

from ..models.base import Base


class DatabaseManager(BaseDatabaseManager):
    def __init__(self, database_url: Optional[str] = None, read_database_url: Optional[str] = None):
        super().__init__(
            application_name="projectcell-qa-agent",
            metadata=Base.metadata,
            database_url=database_url,
            read_database_url=read_database_url,
            logger_name="qa_agent.db",
        )


db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session
