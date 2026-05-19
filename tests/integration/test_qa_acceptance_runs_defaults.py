"""Regression test for `qa_acceptance_runs` JSONB server defaults.

The bug: `files_changed` and `notification_summary` were NOT NULL but had
no server defaults; the SQLAlchemy model declared defaults that only fire
when the column is in the insert value list. Migration
`20260517_qa_acceptance_runs_defaults` added Postgres-side defaults.

This test exercises the exact scenario that previously broke production
inserts: open a session, INSERT with the JSONB columns omitted, and read
the row back. Without the migration the insert would raise
NotNullViolation; with it the row gets ``[]`` and ``{}``.

Precondition: ``alembic upgrade head`` against the test database. The
``migration-test`` CI job satisfies this. Locally, run ``make
migration-test`` or ``alembic upgrade head`` before this file.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.requires_infra, pytest.mark.asyncio]


def _test_database_url() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5433")
    db = os.environ.get("POSTGRES_DB", "wisdoverse-cell_test")
    user = os.environ.get("POSTGRES_USER", "test")
    password = os.environ.get("POSTGRES_PASSWORD", "test")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


async def _ensure_table(engine, table: str) -> None:
    async with engine.connect() as conn:
        present = await conn.run_sync(lambda c: sa.inspect(c).has_table(table))
    if not present:
        pytest.skip(
            f"{table} not present — run `alembic upgrade head` against the "
            "test database before this test"
        )


async def test_insert_with_omitted_jsonb_columns_uses_server_defaults():
    """INSERT omitting files_changed + notification_summary must succeed."""
    engine = create_async_engine(_test_database_url())
    try:
        await _ensure_table(engine, "qa_acceptance_runs")

        run_id = f"run_test_{uuid.uuid4().hex[:12]}"
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO qa_acceptance_runs (
                        id, agent_name, target_path, trigger, level,
                        l0_status, l1_status, l2_status,
                        total_checks, l0_failure_count, l1_warning_count,
                        duration_seconds, runner_exit_code,
                        raw_report, created_at
                    ) VALUES (
                        :id, 'qa-agent', '/tmp/regression-probe', 'manual', 'l0',
                        'PASS', 'PASS', 'PASS', 0, 0, 0,
                        0.0, 0,
                        '{}'::jsonb, NOW()
                    )
                    """
                ),
                {"id": run_id},
            )

        async with engine.connect() as conn:
            files_changed, notification_summary = (
                await conn.execute(
                    sa.text(
                        "SELECT files_changed, notification_summary "
                        "FROM qa_acceptance_runs WHERE id = :id"
                    ),
                    {"id": run_id},
                )
            ).one()

        if isinstance(files_changed, str):
            files_changed = json.loads(files_changed)
        if isinstance(notification_summary, str):
            notification_summary = json.loads(notification_summary)
        assert files_changed == []
        assert notification_summary == {}

        async with engine.begin() as conn:
            await conn.execute(
                sa.text("DELETE FROM qa_acceptance_runs WHERE id = :id"),
                {"id": run_id},
            )
    finally:
        await engine.dispose()


async def test_qa_acceptance_runs_server_defaults_declared_in_schema():
    """Schema-level assertion: the JSONB columns must carry server defaults.

    Catches the case where the migration is dropped — even if the table
    exists at all, the columns must still report a ``server_default``.
    """
    engine = create_async_engine(_test_database_url())
    try:
        await _ensure_table(engine, "qa_acceptance_runs")
        async with engine.connect() as conn:
            columns = await conn.run_sync(
                lambda c: {
                    col["name"]: col
                    for col in sa.inspect(c).get_columns("qa_acceptance_runs")
                }
            )
    finally:
        await engine.dispose()

    files_default = columns["files_changed"].get("default") or ""
    notification_default = columns["notification_summary"].get("default") or ""
    assert "[]" in files_default, (
        f"files_changed missing JSONB default; got default={files_default!r}"
    )
    assert "{}" in notification_default, (
        f"notification_summary missing JSONB default; got default={notification_default!r}"
    )
