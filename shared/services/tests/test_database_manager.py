"""
Tests for BaseDatabaseManager read/write split.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.db.base_database import BaseDatabaseManager

_PATCH_PREFIX = "shared.db.base_database"


@pytest.fixture
def mock_settings():
    with patch(f"{_PATCH_PREFIX}.settings") as ms:
        ms.database_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        ms.database_read_url = None
        ms.debug = False
        ms.db_pool_size = 5
        ms.db_max_overflow = 10
        ms.db_pool_recycle = 1800
        ms.db_pool_timeout = 30
        ms.db_connect_timeout = 10
        ms.db_command_timeout = 60
        yield ms


def _make_db(mock_settings, **kwargs):
    with patch(f"{_PATCH_PREFIX}.create_async_engine") as mock_engine:
        mock_pool = MagicMock()
        mock_pool.size.return_value = 5
        mock_pool.checkedin.return_value = 3
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0
        engine = MagicMock()
        engine.pool = mock_pool
        mock_engine.return_value = engine
        db = BaseDatabaseManager(
            application_name="test-app",
            metadata=MagicMock(),
            **kwargs,
        )
    return db, mock_engine


class TestDatabaseManagerInit:
    def test_init_without_read_replica(self, mock_settings):
        db, _ = _make_db(mock_settings)
        assert db.read_engine is None
        assert db._read_session_factory is None

    def test_init_with_read_replica(self, mock_settings):
        mock_settings.database_read_url = (
            "postgresql+asyncpg://user:pass@replica:5432/testdb"
        )
        db, mock_engine = _make_db(mock_settings)
        assert mock_engine.call_count == 2
        assert db.read_engine is not None
        assert db._read_session_factory is not None

    def test_init_explicit_read_url(self, mock_settings):
        db, mock_engine = _make_db(
            mock_settings,
            read_database_url="postgresql+asyncpg://user:pass@replica:5432/testdb",
        )
        assert mock_engine.call_count == 2
        assert db.read_engine is not None


class TestReadSessionFallback:
    @pytest.mark.asyncio
    async def test_read_session_falls_back_to_primary(self, mock_settings):
        """When no read replica, read_session_ctx uses primary session."""
        db, _ = _make_db(mock_settings)

        mock_session = AsyncMock()
        db.async_session = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        async with db.read_session_ctx() as session:
            assert session is mock_session


class TestPoolStatus:
    def test_pool_status_write_only(self, mock_settings):
        db, _ = _make_db(mock_settings)
        status = db.pool_status()

        assert "write" in status
        assert "read" not in status
        assert status["write"]["size"] == 5

    def test_pool_status_with_read_replica(self, mock_settings):
        mock_settings.database_read_url = (
            "postgresql+asyncpg://user:pass@replica:5432/testdb"
        )
        db, _ = _make_db(mock_settings)
        status = db.pool_status()

        assert "write" in status
        assert "read" in status


class TestClose:
    @pytest.mark.asyncio
    async def test_close_disposes_write_engine(self, mock_settings):
        with patch(f"{_PATCH_PREFIX}.create_async_engine") as mock_engine:
            engine = AsyncMock()
            mock_engine.return_value = engine
            db = BaseDatabaseManager(
                application_name="test-app",
                metadata=MagicMock(),
            )

        await db.close()
        engine.dispose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_disposes_both_engines(self, mock_settings):
        mock_settings.database_read_url = (
            "postgresql+asyncpg://user:pass@replica:5432/testdb"
        )
        with patch(f"{_PATCH_PREFIX}.create_async_engine") as mock_engine:
            write_engine = AsyncMock()
            read_engine = AsyncMock()
            mock_engine.side_effect = [write_engine, read_engine]
            db = BaseDatabaseManager(
                application_name="test-app",
                metadata=MagicMock(),
            )

        await db.close()
        write_engine.dispose.assert_awaited_once()
        read_engine.dispose.assert_awaited_once()
