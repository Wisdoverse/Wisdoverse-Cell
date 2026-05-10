"""Integration test fixtures — sync_module.

Real database session connecting to PostgreSQL for integration tests.
"""
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.capabilities.sync.models.base import Base
from shared.capabilities.sync.models.sync import (  # noqa: F401
    SubtaskMapping,
    SyncLock,
    SyncLog,
    SyncMapping,
)

os.environ.setdefault("POSTGRES_HOST", "localhost")
# Local dev uses 5433 to avoid conflict with host PostgreSQL; CI sets POSTGRES_PORT=5432 via env
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "wisdoverse-cell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Real database session with per-test transaction rollback."""
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5433")
    pg_db = os.environ.get("POSTGRES_DB", "wisdoverse-cell_test")
    pg_user = os.environ.get("POSTGRES_USER", "test")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "test")
    database_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except (OSError, OperationalError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL integration database unavailable: {exc}")

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
