"""Database manager for the shared control-plane ledger."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_database import BaseDatabaseManager

from .tables import control_plane_metadata


class ControlPlaneDatabaseManager(BaseDatabaseManager):
    def __init__(
        self,
        database_url: str | None = None,
        read_database_url: str | None = None,
    ):
        super().__init__(
            application_name="projectcell-control-plane",
            metadata=control_plane_metadata,
            database_url=database_url,
            read_database_url=read_database_url,
            logger_name="control_plane.db",
        )


control_plane_db_manager = ControlPlaneDatabaseManager()


async def get_control_plane_db() -> AsyncGenerator[AsyncSession, None]:
    async with control_plane_db_manager.session() as session:
        yield session
