"""DSAR Service unit tests.

Covers:
- Export collects from all tables
- Dry-run delete reports counts without deleting
- Confirmed delete actually removes records
- Redis key cleanup
- Partial failure handling (one table fails, others still process)
"""
from __future__ import annotations

from typing import Any, Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.dsar import DSARHandler, DSARService, TableSpec, _hash_uid
from shared.schemas.dsar import DSARResult

# ---------------------------------------------------------------------------
# Fixtures: in-memory handler with mock session / redis
# ---------------------------------------------------------------------------

class FakeHandler(DSARHandler):
    """Test handler with configurable table specs and redis patterns."""

    def __init__(
        self,
        specs: Sequence[TableSpec] | None = None,
        redis_patterns: Sequence[str] | None = None,
        session: Any = None,
        redis_client: Any = None,
    ):
        self._specs = list(specs or [])
        self._patterns = list(redis_patterns or [])
        self._session = session
        self._redis = redis_client

    def table_specs(self) -> Sequence[TableSpec]:
        return self._specs

    def redis_key_patterns(self) -> Sequence[str]:
        return self._patterns

    async def get_session(self):
        return self._session

    def get_redis(self):
        return self._redis


def _make_mock_session(table_data: dict[str, list[dict]] | None = None):
    """Build a mock AsyncSession that responds to textual SELECTs/DELETEs.

    ``table_data`` maps table_name -> list of row dicts.
    """
    table_data = table_data or {}

    async def _execute(stmt, *_args, **_kwargs):
        sql = str(stmt) if not hasattr(stmt, "text") else str(stmt.text)

        # SELECT count(*)
        if "count(*)" in sql.lower():
            for tname, rows in table_data.items():
                if tname in sql:
                    result = MagicMock()
                    result.scalar_one.return_value = len(rows)
                    return result
            result = MagicMock()
            result.scalar_one.return_value = 0
            return result

        # SELECT *
        if sql.strip().upper().startswith("SELECT"):
            for tname, rows in table_data.items():
                if tname in sql:
                    # Return dicts directly via mappings API
                    result = MagicMock()
                    result.mappings.return_value.all.return_value = rows
                    return result
            result = MagicMock()
            result.mappings.return_value.all.return_value = []
            return result

        # DELETE
        if sql.strip().upper().startswith("DELETE"):
            for tname, rows in table_data.items():
                if tname in sql:
                    result = MagicMock()
                    result.rowcount = len(rows)
                    # simulate deletion
                    table_data[tname] = []
                    return result
            result = MagicMock()
            result.rowcount = 0
            return result

        result = MagicMock()
        result.scalar_one.return_value = 0
        result.rowcount = 0
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()
    session.close = AsyncMock()
    return session


def _make_mock_redis(existing_keys: list[str] | None = None):
    """Build a mock Redis client with scan_iter and delete support."""
    existing = set(existing_keys or [])
    r = AsyncMock()

    async def _scan_iter(match: str = "*", count: int = 100):
        import fnmatch
        for key in list(existing):
            if fnmatch.fnmatch(key, match):
                yield key

    r.scan_iter = _scan_iter
    r.delete = AsyncMock(side_effect=lambda *keys: existing.difference_update(keys))
    r._existing = existing  # expose for assertions
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHashUid:
    def test_deterministic(self):
        assert _hash_uid("user123") == _hash_uid("user123")

    def test_not_plaintext(self):
        assert "user123" not in _hash_uid("user123")

    def test_fixed_length(self):
        assert len(_hash_uid("anything")) == 16


class TestDSARExport:
    @pytest.mark.asyncio
    async def test_export_collects_all_tables(self):
        """Export should return data from every registered table."""
        table_data = {
            "chat_agent_conversation_histories": [
                {"id": 1, "user_id": "u1", "messages": "[]"},
            ],
            "chat_agent_card_operations": [
                {"id": 10, "user_id": "u1", "action": "approve"},
                {"id": 11, "user_id": "u1", "action": "reject"},
            ],
        }
        session = _make_mock_session(table_data)
        handler = FakeHandler(
            specs=[
                TableSpec("chat_agent_conversation_histories"),
                TableSpec("chat_agent_card_operations"),
            ],
            session=session,
        )
        svc = DSARService(handler)
        result = await svc.export_user_data("u1")

        assert "chat_agent_conversation_histories" in result
        assert len(result["chat_agent_conversation_histories"]) == 1
        assert "chat_agent_card_operations" in result
        assert len(result["chat_agent_card_operations"]) == 2

    @pytest.mark.asyncio
    async def test_export_empty(self):
        """Export with no matching data returns empty lists."""
        session = _make_mock_session({})
        handler = FakeHandler(
            specs=[TableSpec("some_table")],
            session=session,
        )
        svc = DSARService(handler)
        result = await svc.export_user_data("nobody")
        assert result["some_table"] == []


class TestDSARDeleteDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_reports_counts(self):
        """Dry-run should report counts without actually deleting."""
        table_data = {
            "chat_agent_conversation_histories": [
                {"id": 1, "user_id": "u1"},
            ],
            "chat_agent_daily_progress": [
                {"id": 2, "user_id": "u1"},
                {"id": 3, "user_id": "u1"},
            ],
        }
        session = _make_mock_session(table_data)
        handler = FakeHandler(
            specs=[
                TableSpec("chat_agent_conversation_histories"),
                TableSpec("chat_agent_daily_progress"),
            ],
            session=session,
        )
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=True)

        assert isinstance(result, DSARResult)
        assert result.action == "delete_dry_run"
        assert result.affected_tables["chat_agent_conversation_histories"] == 1
        assert result.affected_tables["chat_agent_daily_progress"] == 2
        assert result.status == "completed"
        # Data should NOT have been deleted (no DELETE executed)
        # The table_data dicts should still have entries
        assert len(table_data["chat_agent_conversation_histories"]) == 1

    @pytest.mark.asyncio
    async def test_dry_run_no_commit(self):
        """Dry-run should not call session.commit()."""
        session = _make_mock_session({"t": [{"id": 1, "user_id": "u1"}]})
        handler = FakeHandler(specs=[TableSpec("t")], session=session)
        svc = DSARService(handler)
        await svc.delete_user_data("u1", dry_run=True)
        session.commit.assert_not_awaited()


class TestDSARDeleteConfirmed:
    @pytest.mark.asyncio
    async def test_confirmed_delete_removes_records(self):
        """Confirmed delete should actually remove records."""
        table_data = {
            "chat_agent_conversation_histories": [
                {"id": 1, "user_id": "u1"},
            ],
        }
        session = _make_mock_session(table_data)
        handler = FakeHandler(
            specs=[TableSpec("chat_agent_conversation_histories")],
            session=session,
        )
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=False)

        assert result.action == "delete"
        assert result.affected_tables["chat_agent_conversation_histories"] == 1
        assert result.status == "completed"
        # mock simulates clearing the list
        assert len(table_data["chat_agent_conversation_histories"]) == 0
        session.commit.assert_awaited_once()


class TestDSARRedisCleanup:
    @pytest.mark.asyncio
    async def test_redis_keys_counted_in_dry_run(self):
        """Dry-run should count matching Redis keys."""
        redis_client = _make_mock_redis([
            "pending_op:abc123",
            "pending_op:def456",
            "chat:user_info:u1hash",
            "unrelated:key",
        ])
        session = _make_mock_session({})
        handler = FakeHandler(
            specs=[],
            redis_patterns=["pending_op:*", "chat:user_info:*"],
            session=session,
            redis_client=redis_client,
        )
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=True)

        assert result.redis_keys_affected == 3  # pending_op:* x2 + user_info:* x1
        # Keys should NOT have been deleted
        assert len(redis_client._existing) == 4

    @pytest.mark.asyncio
    async def test_redis_keys_deleted_on_confirm(self):
        """Confirmed delete should remove matching Redis keys."""
        redis_client = _make_mock_redis([
            "pending_op:abc123",
            "chat:user_info:u1hash",
            "unrelated:key",
        ])
        session = _make_mock_session({})
        handler = FakeHandler(
            specs=[],
            redis_patterns=["pending_op:*", "chat:user_info:*"],
            session=session,
            redis_client=redis_client,
        )
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=False)

        assert result.redis_keys_affected == 2
        redis_client.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_redis_client(self):
        """Handler with no Redis should report 0 keys."""
        session = _make_mock_session({})
        handler = FakeHandler(specs=[], session=session, redis_client=None)
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=True)
        assert result.redis_keys_affected == 0


class TestDSARPartialFailure:
    @pytest.mark.asyncio
    async def test_one_table_fails_others_succeed(self):
        """If one table errors, other tables should still be processed."""
        table_data = {
            "good_table": [{"id": 1, "user_id": "u1"}],
        }
        session = _make_mock_session(table_data)

        # Wrap execute to fail on bad_table
        original_execute = session.execute

        async def _failing_execute(stmt, *args, **kwargs):
            sql = str(stmt) if not hasattr(stmt, "text") else str(stmt.text)
            if "bad_table" in sql:
                raise RuntimeError("connection lost")
            return await original_execute(stmt, *args, **kwargs)

        session.execute = AsyncMock(side_effect=_failing_execute)

        handler = FakeHandler(
            specs=[
                TableSpec("bad_table"),
                TableSpec("good_table"),
            ],
            session=session,
        )
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=True)

        assert result.status == "partial_failure"
        assert len(result.errors) == 1
        assert "bad_table" in result.errors[0]
        # good_table should still have its count
        assert result.affected_tables["good_table"] == 1

    @pytest.mark.asyncio
    async def test_redis_failure_is_partial(self):
        """Redis error should result in partial_failure, not crash."""
        session = _make_mock_session({})

        redis_client = AsyncMock()

        async def _broken_scan(*_a, **_kw):
            raise ConnectionError("Redis down")
            yield  # pragma: no cover — unreachable, makes this an async generator

        redis_client.scan_iter = _broken_scan

        handler = FakeHandler(
            specs=[],
            redis_patterns=["key:*"],
            session=session,
            redis_client=redis_client,
        )
        svc = DSARService(handler)
        result = await svc.delete_user_data("u1", dry_run=True)

        assert result.status == "partial_failure"
        assert any("redis" in e.lower() for e in result.errors)


class TestDSARResultSchema:
    def test_schema_fields(self):
        r = DSARResult(
            user_id="u1",
            action="delete",
            affected_tables={"t1": 5},
            redis_keys_affected=2,
            status="completed",
        )
        assert r.user_id == "u1"
        assert r.action == "delete"
        assert r.affected_tables == {"t1": 5}
        assert r.redis_keys_affected == 2
        assert r.timestamp  # auto-generated

    def test_schema_serialization(self):
        r = DSARResult(
            user_id="u1",
            action="export",
            affected_tables={},
            redis_keys_affected=0,
            status="completed",
        )
        data = r.model_dump()
        assert isinstance(data["timestamp"], str)
        assert data["errors"] == []

    def test_idempotent_results(self):
        """Same input should produce consistent output (minus timestamp)."""
        kwargs = dict(
            user_id="u1",
            action="delete_dry_run",
            affected_tables={"t": 3},
            redis_keys_affected=1,
            status="completed",
        )
        r1 = DSARResult(**kwargs)
        r2 = DSARResult(**kwargs)
        assert r1.affected_tables == r2.affected_tables
        assert r1.action == r2.action
