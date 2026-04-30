"""
Shared DatabaseManager base class for all agents.

Each agent instantiates with its own application_name and metadata.
Supports optional read replica for read/write split.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import MetaData
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.utils.logger import get_logger


class BaseDatabaseManager:
    def __init__(
        self,
        application_name: str,
        metadata: MetaData,
        database_url: Optional[str] = None,
        read_database_url: Optional[str] = None,
        logger_name: str = "db",
    ):
        self._logger = get_logger(logger_name)
        self._metadata = metadata
        self._database_url: Optional[str] = database_url or settings.database_url

        # Write engine (primary)
        self.engine = create_async_engine(
            self._database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            pool_timeout=settings.db_pool_timeout,
            connect_args={
                "timeout": settings.db_connect_timeout,
                "command_timeout": settings.db_command_timeout,
                "server_settings": {"application_name": application_name},
            },
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # Read engine (replica, optional)
        _read_url = read_database_url or settings.database_read_url
        self.read_engine = None
        self._read_session_factory = None
        if _read_url:
            self.read_engine = create_async_engine(
                _read_url,
                echo=settings.debug,
                pool_pre_ping=True,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_recycle=settings.db_pool_recycle,
                pool_timeout=settings.db_pool_timeout,
                connect_args={
                    "timeout": settings.db_connect_timeout,
                    "command_timeout": settings.db_command_timeout,
                    "server_settings": {"application_name": f"{application_name}-ro"},
                },
            )
            self._read_session_factory = async_sessionmaker(
                self.read_engine, class_=AsyncSession, expire_on_commit=False,
            )
            _safe_url = make_url(_read_url).set(password="***")
            self._logger.info("read_replica_configured", read_url=str(_safe_url))

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(self._metadata.create_all)
        self._logger.info("database_tables_created")

    async def drop_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(self._metadata.drop_all)
        self._logger.info("database_tables_dropped")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Write database session (primary)."""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def read_session_ctx(self) -> AsyncGenerator[AsyncSession, None]:
        """Read-only database session (replica, fallback to primary)."""
        factory = self._read_session_factory or self.async_session
        async with factory() as session:
            yield session

    def pool_status(self) -> dict:
        """Return connection pool statistics for health checks."""
        pool = self.engine.pool
        status = {
            "write": {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            },
        }
        if self.read_engine:
            rpool = self.read_engine.pool
            status["read"] = {
                "size": rpool.size(),
                "checked_in": rpool.checkedin(),
                "checked_out": rpool.checkedout(),
                "overflow": rpool.overflow(),
            }
        return status

    async def close(self):
        await self.engine.dispose()
        if self.read_engine:
            await self.read_engine.dispose()
        self._logger.info("database_connection_closed")
