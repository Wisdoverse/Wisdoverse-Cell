"""Test fixtures for the shared control-plane ledger."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

aiosqlite = pytest.importorskip("aiosqlite", reason="aiosqlite not installed")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.control_plane.tables import control_plane_metadata

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.drop_all)

    await engine.dispose()
