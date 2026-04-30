"""
Test fixtures for collaboration pattern tests.

Uses SQLite in-memory database for fast, isolated tests.
"""

from typing import AsyncGenerator

import pytest
import pytest_asyncio

aiosqlite = pytest.importorskip("aiosqlite", reason="aiosqlite not installed")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.evolution.db.tables import evolution_metadata

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async session backed by an in-memory SQLite database."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(evolution_metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(evolution_metadata.drop_all)

    await engine.dispose()
