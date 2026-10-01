"""Real PostgreSQL18 acceptance, fault recovery, drift rejection and isolation."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import dev_migration_rehearsal as rehearsal_module
from scripts.dev_migration_rehearsal import (
    SCHEMA_PREFIX,
    RehearsalFailure,
    candidate_config,
    checked_config,
    fresh_round_trip,
    inherited_fixture,
    parse_database_url,
    run_rehearsal,
    set_scope,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_infra]
DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
CONTAINER = os.environ.get("POSTGRES_CONTAINER")


@pytest.fixture
async def database():
    if not DATABASE_URL:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL18 migration acceptance")
    engine = create_async_engine(parse_database_url(DATABASE_URL))
    sentinel = "s41_public_test_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.execute(
            text(f'CREATE TABLE public."{sentinel}" (id INTEGER PRIMARY KEY, value TEXT)')
        )
        await connection.execute(text(f"INSERT INTO public.\"{sentinel}\" VALUES (1, 'untouched')"))
    try:
        yield engine, sentinel
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP TABLE public."{sentinel}"'))
        await engine.dispose()


async def rehearsal_schemas(engine):
    async with engine.connect() as connection:
        return set(
            (
                await connection.execute(
                    text("SELECT nspname FROM pg_namespace WHERE starts_with(nspname, :prefix)"),
                    {"prefix": SCHEMA_PREFIX},
                )
            ).scalars()
        )


async def assert_public_sentinel(engine, sentinel):
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text(f'SELECT value FROM public."{sentinel}" WHERE id = 1'))
            == "untouched"
        )


async def test_complete_postgresql_rehearsal_restores_after_loss_and_leaves_public_untouched(
    database,
):
    engine, sentinel = database
    before = await rehearsal_schemas(engine)
    result = await run_rehearsal(DATABASE_URL, container=CONTAINER)
    assert result["status"] == "passed"
    assert all(value == "passed" for value in result["checks"].values())
    assert {
        "backup_restore",
        "failure_atomicity",
        "schema_cleanup",
        "drift_rejected",
        "restored_tracking_round_trip",
    }.issubset(result["checks"])
    assert await rehearsal_schemas(engine) == before
    await assert_public_sentinel(engine, sentinel)
    assert DATABASE_URL not in json.dumps(result)


@pytest.mark.parametrize(
    "phase",
    ["migration_checks", "backup", "destructive_loss", "restore", "restore_validation", "complete"],
)
async def test_orchestration_failures_clean_up_committed_schemas_and_preserve_other_runtime(
    database, phase
):
    engine, sentinel = database
    before = await rehearsal_schemas(engine)
    with pytest.raises(RehearsalFailure) as failed:
        await run_rehearsal(DATABASE_URL, container=CONTAINER, fail_at=phase)
    report = failed.value.report
    assert report["status"] == "failed"
    assert report["phase"] == phase
    assert report["checks"]["schema_cleanup"] == "passed"
    assert await rehearsal_schemas(engine) == before
    await assert_public_sentinel(engine, sentinel)


@pytest.mark.parametrize(
    "ddl",
    [
        "ALTER TABLE dev_agent_event_outbox ALTER COLUMN attempts SET DEFAULT 2",
        "ALTER TABLE dev_agent_event_outbox ALTER COLUMN event_type DROP NOT NULL",
        "ALTER TABLE dev_agent_tasks DROP CONSTRAINT ck_dev_status",
        "ALTER TABLE dev_agent_workflow_logs DROP CONSTRAINT dev_agent_workflow_logs_task_id_fkey",
    ],
)
async def test_actual_constraint_drift_is_rejected_before_stamp(database, ddl):
    engine, sentinel = database
    schema = SCHEMA_PREFIX + uuid4().hex
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await set_scope(connection, schema)
        expected = await connection.run_sync(lambda conn: fresh_round_trip(conn, schema))
        await connection.run_sync(inherited_fixture)
        await connection.execute(text(ddl))
        with pytest.raises(RuntimeError, match="drift detected"):
            await connection.run_sync(
                lambda conn: command.stamp(checked_config(conn, expected, schema), "head")
            )
        assert not await connection.run_sync(
            lambda conn: inspect(conn).has_table("alembic_version_dev_agent")
        )
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "legacy_head_sentinel"
        )
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await assert_public_sentinel(engine, sentinel)


async def test_candidate_refuses_public_schema_and_public_fallback(database):
    engine, sentinel = database
    schema = SCHEMA_PREFIX + uuid4().hex
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text("SET LOCAL search_path TO public"))
        with pytest.raises(RuntimeError, match="wrong schema"):
            await connection.run_sync(
                lambda conn: command.upgrade(candidate_config(conn, schema=schema), "head")
            )
        await connection.execute(
            text("SELECT set_config('search_path', :path, true)"), {"path": f"{schema}, public"}
        )
        with pytest.raises(RuntimeError, match="exclude other schemas"):
            await connection.run_sync(
                lambda conn: command.upgrade(candidate_config(conn, schema=schema), "head")
            )
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await assert_public_sentinel(engine, sentinel)


async def test_concurrent_cli_runs_use_independent_schemas(database):
    engine, sentinel = database
    before = await rehearsal_schemas(engine)
    env = os.environ.copy()
    env.pop("REHEARSAL_REPORT", None)
    processes = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "scripts.dev_migration_rehearsal",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        for _ in range(2)
    ]
    try:
        outputs = await asyncio.wait_for(
            asyncio.gather(*(process.communicate() for process in processes)), timeout=40
        )
        for process, (stdout, stderr) in zip(processes, outputs, strict=True):
            assert process.returncode == 0, stderr.decode()
            assert json.loads(stdout)["status"] == "passed"
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()
    assert await rehearsal_schemas(engine) == before
    await assert_public_sentinel(engine, sentinel)


async def test_changed_source_invalidates_acceptance_and_cleans_up(database, monkeypatch):
    engine, sentinel = database
    before = await rehearsal_schemas(engine)
    original = rehearsal_module.source_identity
    calls = 0

    def changed_identity():
        nonlocal calls
        calls += 1
        identity = original()
        if calls > 1:
            identity["inputs_sha256"] = "changed-during-verification"
        return identity

    monkeypatch.setattr(rehearsal_module, "source_identity", changed_identity)
    with pytest.raises(RehearsalFailure) as failed:
        await run_rehearsal(DATABASE_URL, container=CONTAINER)
    assert failed.value.report["phase"] == "source_verification"
    assert failed.value.report["checks"]["schema_cleanup"] == "passed"
    assert await rehearsal_schemas(engine) == before
    await assert_public_sentinel(engine, sentinel)


async def test_corrupted_backup_restore_fails_closed_and_cleans_up(database, monkeypatch):
    engine, sentinel = database
    before = await rehearsal_schemas(engine)
    original = rehearsal_module.client_operation

    async def corrupted_restore(program, url, container, args, data=None):
        if program == "pg_restore":
            data = b"PGDMPinvalid-archive"
        return await original(program, url, container, args, data)

    monkeypatch.setattr(rehearsal_module, "client_operation", corrupted_restore)
    with pytest.raises(RehearsalFailure) as failed:
        await run_rehearsal(DATABASE_URL, container=CONTAINER)
    assert failed.value.report["phase"] == "restore"
    assert failed.value.report["checks"]["schema_cleanup"] == "passed"
    assert "invalid-archive" not in json.dumps(failed.value.report)
    assert await rehearsal_schemas(engine) == before
    await assert_public_sentinel(engine, sentinel)
