"""
Unit Test Fixtures

Provides database sessions and other fixtures for unit tests.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path before other imports.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Test environment configuration.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "wisdoverse-cell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

# Import all models so SQLAlchemy registers them.
from agents.requirement_manager.models import (
    Base,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Test database session.

    Each test uses an isolated transaction that is rolled back at teardown.
    """
    # Create the test database engine.
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5433")
    pg_db = os.environ.get("POSTGRES_DB", "wisdoverse-cell_test")
    pg_user = os.environ.get("POSTGRES_USER", "test")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "test")
    database_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    engine = create_async_engine(database_url, echo=False)

    # Create tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create the session factory.
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Roll back after the test.
        await session.rollback()

    # Drop tables after the test.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def sample_usage_data():
    """Sample LLM usage data."""
    return {
        "agent_id": "requirement-manager",
        "task_type": "extraction",
        "model": "claude-sonnet-4-20250514",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd": 0.0105,
        "latency_ms": 1200,
        "success": True
    }
