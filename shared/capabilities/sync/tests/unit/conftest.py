"""Unit test fixtures — sync_agent.

Mock database session for pure unit tests (no PostgreSQL required).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def db_session():
    """Mock async database session for unit tests."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        scalar_one_or_none=MagicMock(return_value=None),
    ))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session
