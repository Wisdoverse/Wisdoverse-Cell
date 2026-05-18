"""
Unit Test Fixtures - chat_agent

Database sessions and fixtures for unit tests.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path before other imports.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock

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
from services.gateways.user_interaction.models.base import Base
from services.gateways.user_interaction.models.card_operation import CardOperation  # noqa: F401
from services.gateways.user_interaction.models.conversation import ConversationHistory  # noqa: F401
from services.gateways.user_interaction.models.daily_progress import DailyProgress  # noqa: F401
from services.gateways.user_interaction.models.event_outbox import (
    UserInteractionEventOutbox,  # noqa: F401
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session for tests.

    Each test uses an isolated transaction and rolls it back after completion.
    """
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
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        # Roll back after the test.
        await session.rollback()

    # Drop tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_event_bus():
    """Mock EventBus"""
    bus = AsyncMock()
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    bus.is_connected = True
    return bus


@pytest.fixture
def mock_chat_service():
    """Mock ChatService"""
    service = AsyncMock()
    service.chat = AsyncMock(return_value="mock reply")
    service.chat_with_user_assistant = AsyncMock(return_value="mock reply")
    service.clear_history = AsyncMock()
    return service
