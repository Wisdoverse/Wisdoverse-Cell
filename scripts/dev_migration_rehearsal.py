"""Dev S4.1 engineering acceptance on disposable PostgreSQL, with bounded operations.

Only generated synthetic schemas are touched. Backups are private temporary files.
Reports contain checks and source identity, never connection URLs or row payloads.
The runtime's shared migration owner remains active until a separate cutover.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from agents.dev_agent.migrations.contracts import (
    OWNED_TABLES,
    REVISION,
    SCHEMA_PREFIX,
    VERSION_TABLE,
    schema_inventory,
)

ROOT = Path(__file__).resolve().parents[1]
TABLES = OWNED_TABLES
HEAD = REVISION
PROTECTED_TABLES = ("alembic_version", "other_runtime_records")
ALL_TABLES = (*TABLES, VERSION_TABLE, *PROTECTED_TABLES)
TOOL_TIMEOUT_SECONDS = 60


class RehearsalFailure(RuntimeError):
    """Safe failure details for CI; underlying database/client output is withheld."""

    def __init__(self, report: dict[str, Any]):
        super().__init__(f"Dev rehearsal failed at {report['phase']}")
        self.report = report


class InjectedFailure(RuntimeError):
    pass


def candidate_config(
    connection: Connection | None, *, schema: str | None = None, destructive: bool = False
) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ROOT / "agents/dev_agent/migrations"))
    config.attributes.update(
        connection=connection,
        rehearsal_schema=schema,
        sqlite_unit_test=connection is not None and connection.dialect.name == "sqlite",
        allow_destructive_baseline=destructive,
    )
    return config


def snapshot(connection: Connection) -> dict[str, Any]:
    """Internal synthetic-only comparison, never included in public evidence."""
    inspector = inspect(connection)
    return {
        table: connection.execute(
            text(
                f"SELECT * FROM {table} ORDER BY "
                + ", ".join(inspector.get_pk_constraint(table)["constrained_columns"])
            )
        ).all()
        for table in ALL_TABLES
    }


def fresh_round_trip(connection: Connection, schema: str | None = None) -> dict[str, Any]:
    if inspect(connection).get_table_names():
        raise RuntimeError("Rehearsal requires an empty isolated schema")
    config = candidate_config(connection, schema=schema, destructive=True)
    command.upgrade(config, "head")
    fresh = schema_inventory(connection)
    if set(inspect(connection).get_table_names()) != {*TABLES, VERSION_TABLE}:
        raise RuntimeError("Candidate chain modified tables outside Dev ownership")
    if connection.scalar(text(f"SELECT version_num FROM {VERSION_TABLE}")) != HEAD:
        raise RuntimeError("Candidate revision does not match expected head")
    command.downgrade(config, "base")
    if set(inspect(connection).get_table_names()) != {VERSION_TABLE}:
        raise RuntimeError("Candidate downgrade left owned tables behind")
    command.upgrade(config, "head")
    if schema_inventory(connection) != fresh:
        raise RuntimeError("Candidate schema changed after round trip")
    command.downgrade(config, "base")
    connection.execute(text(f"DROP TABLE {VERSION_TABLE}"))
    return fresh


def inherited_fixture(connection: Connection) -> None:
    # Materialize the legacy DDL through Alembic's supported operation context;
    # the candidate remains a frozen independent copy, not a legacy import.
    from importlib import import_module

    legacy = import_module("migrations.versions.20260504_runtime_tables")
    outbox = import_module("migrations.versions.20260512_dev_event_outbox")
    with Operations.context(MigrationContext.configure(connection)):
        legacy._create_dev_tables()
        outbox.upgrade()
    connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)"))
    connection.execute(text("INSERT INTO alembic_version VALUES ('legacy_head_sentinel')"))
    connection.execute(
        text("CREATE TABLE other_runtime_records (id INTEGER PRIMARY KEY, state VARCHAR(32))")
    )
    connection.execute(text("INSERT INTO other_runtime_records VALUES (1, 'untouched')"))
    connection.execute(
        text("INSERT INTO dev_agent_tasks (id, wp_id, status) VALUES ('task_probe', 1, 'pending')")
    )
    connection.execute(
        text(
            "INSERT INTO dev_agent_workflow_logs (id, task_id, workflow_json) VALUES ('log_probe', 'task_probe', '{}')"
        )
    )
    connection.execute(
        text("""INSERT INTO dev_agent_event_outbox
        (event_id, event_type, source_agent, payload, created_at)
        VALUES ('evt_probe', 'dev.task_created', 'dev-agent', '{}', CURRENT_TIMESTAMP)""")
    )


def checked_config(
    connection: Connection, expected: dict[str, Any], schema: str | None = None
) -> Config:
    config = candidate_config(connection, schema=schema)
    config.attributes["inherited_inventory"] = expected
    return config


def tracking_round_trip(connection: Connection, config: Config) -> None:
    before = snapshot(connection)
    command.stamp(config, "base")
    if connection.scalar(text(f"SELECT COUNT(*) FROM {VERSION_TABLE}")) != 0:
        raise RuntimeError("Tracking rollback did not clear candidate revision")
    command.stamp(config, "head")
    command.upgrade(config, "head")
    if snapshot(connection) != before:
        raise RuntimeError("Tracking rollback/restamp changed inherited state")


def failure_and_drift_probes(connection: Connection, config: Config) -> None:
    before = snapshot(connection)
    try:
        with connection.begin_nested():
            command.stamp(config, "base")
            connection.execute(text("CREATE TABLE interrupted_cutover (id INTEGER)"))
            raise InjectedFailure("Intentional failure after version mutation and DDL")
    except InjectedFailure:
        pass
    if snapshot(connection) != before or inspect(connection).has_table("interrupted_cutover"):
        raise RuntimeError("Failed cutover did not roll back atomically")
    try:
        with connection.begin_nested():
            connection.execute(text("DROP INDEX idx_dev_tasks_workflow_id"))
            command.stamp(config, "head")
    except RuntimeError as error:
        if str(error) != "Inherited Dev schema drift detected":
            raise
    else:
        raise RuntimeError("Drifted inherited schema was stamped")
    if snapshot(connection) != before:
        raise RuntimeError("Drift rejection changed inherited state")
    try:
        with connection.begin_nested():
            command.downgrade(config, "base")
    except RuntimeError as error:
        if "restricted to the fresh-schema rehearsal" not in str(error):
            raise
    else:
        raise RuntimeError("Inherited baseline allowed destructive downgrade")
    if snapshot(connection) != before:
        raise RuntimeError("Downgrade rejection changed inherited state")


def rehearse(connection: Connection, schema: str | None = None) -> dict[str, Any]:
    """Portable DDL/tracking checks; PostgreSQL CLI adds loss/restore and teardown."""
    fresh = fresh_round_trip(connection, schema)
    inherited_fixture(connection)
    config = checked_config(connection, fresh, schema)
    command.stamp(config, "head")
    command.upgrade(config, "head")
    tracking_round_trip(connection, config)
    failure_and_drift_probes(connection, config)
    if schema_inventory(connection) != fresh:
        raise RuntimeError("Inherited Dev schema differs from fresh baseline")
    return {
        "fresh_round_trip": "passed",
        "inherited_schema_parity": "passed",
        "stamp_rollback_restamp": "passed",
        "failure_atomicity": "passed",
        "drift_rejected": "passed",
        "destructive_downgrade_rejected": "passed",
        "legacy_version_preserved": "passed",
        "other_runtime_preserved": "passed",
    }


def parse_database_url(raw: str | None) -> URL:
    try:
        url = make_url(raw or "")
    except Exception:
        raise ValueError(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL database using asyncpg"
        ) from None
    if (
        url.drivername != "postgresql+asyncpg"
        or not url.host
        or not url.database
        or not url.username
        or url.query
    ):
        raise ValueError(
            "TEST_DATABASE_URL requires asyncpg, host, database and username without query parameters"
        )
    return url


def postgres_client(
    program: str, url: URL, container: str | None
) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    # Explicit libpq selectors keep local clients on the same database, even
    # when the process inherits a different PG service configuration.
    for key in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGHOSTADDR"):
        env.pop(key, None)
    env.update(
        PGHOST=url.host or "",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database or "",
        PGCONNECT_TIMEOUT="10",
    )
    if container:
        for key in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        ):
            env.pop(key, None)
        args = [
            "docker",
            "--host=unix:///var/run/docker.sock",
            "exec",
            "-i",
            "-e",
            "PGUSER",
            "-e",
            "PGPASSWORD",
            "-e",
            "PGDATABASE",
            container,
            program,
            "--host=127.0.0.1",
            "--port=5432",
        ]
    else:
        args = [program]
    return args, env


async def client_operation(
    program: str, url: URL, container: str | None, args: list[str], data: bytes | None = None
) -> bytes:
    command_args, env = postgres_client(program, url, container)
    process = await asyncio.create_subprocess_exec(
        *command_args,
        *args,
        env=env,
        stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(data), TOOL_TIMEOUT_SECONDS)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(f"{program} failed; client output withheld")
    return output


async def set_scope(connection: AsyncConnection, schema: str) -> None:
    await connection.execute(
        text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
    )


def source_identity() -> dict[str, Any]:
    paths = [
        "scripts/dev_migration_rehearsal.py",
        "Makefile",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "migrations/versions/20260504_runtime_tables.py",
        "migrations/versions/20260512_dev_event_outbox.py",
    ]
    paths.extend(
        str(path.relative_to(ROOT)) for path in (ROOT / "agents/dev_agent/migrations").rglob("*.py")
    )
    paths.extend(
        str(path.relative_to(ROOT)) for path in (ROOT / "tests").rglob("test_dev_migration*.py")
    )
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode() + b"\0" + (ROOT / path).read_bytes() + b"\0")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    )
    return {
        "base_commit": revision,
        "worktree_dirty": dirty,
        "inputs_sha256": digest.hexdigest(),
        "input_files": sorted(paths),
    }


async def run_rehearsal(
    raw_url: str | None, *, container: str | None = None, fail_at: str | None = None
) -> dict[str, Any]:
    url = parse_database_url(raw_url)
    schema = SCHEMA_PREFIX + uuid4().hex
    engine = create_async_engine(url, connect_args={"timeout": 10, "command_timeout": 30})
    started = monotonic()
    created = False
    report: dict[str, Any] = {
        "format_version": "1.0",
        "milestone": "S4.1",
        "runtime": "dev-agent",
        "candidate_revision": HEAD,
        "rehearsal_schema": schema,
        "evidence_scope": "synthetic_engineering_acceptance",
        "verified_at": datetime.now(UTC).isoformat(),
        "source": source_identity(),
        "owned_tables": list(TABLES),
        "checks": {},
        "status": "running",
        "phase": "create_schema",
    }
    failure: Exception | None = None

    def phase(name: str) -> None:
        report["phase"] = name
        if fail_at == name:
            raise InjectedFailure("Intentional orchestration failure")

    try:
        async with engine.begin() as connection:
            report["postgres_version"] = await connection.scalar(text("SHOW server_version"))
            if int(str(report["postgres_version"]).split(".")[0]) < 18:
                raise RuntimeError("PostgreSQL 18 or newer is required for engineering acceptance")
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            # Also clean up if commit succeeds server-side but its acknowledgement
            # fails. A rolled-back CREATE is harmless to DROP IF EXISTS.
            created = True
        phase("migration_checks")
        async with engine.begin() as connection:
            await set_scope(connection, schema)
            report["checks"].update(await connection.run_sync(lambda conn: rehearse(conn, schema)))
            inventory_before = await connection.run_sync(
                lambda conn: schema_inventory(conn, ALL_TABLES)
            )
            rows_before = await connection.run_sync(snapshot)
        phase("backup")
        with tempfile.TemporaryDirectory(prefix="dev_migration_backup_") as directory:
            backup = Path(directory) / "synthetic.dump"
            archive = await client_operation(
                "pg_dump",
                url,
                container,
                [
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--strict-names",
                    f"--schema={schema}",
                ],
            )
            backup.write_bytes(archive)
            backup.chmod(0o600)
            if not archive.startswith(b"PGDMP"):
                raise RuntimeError("Backup is not a PostgreSQL custom archive")
            report["checks"]["backup_created"] = "passed"
            phase("destructive_loss")
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            phase("restore")
            await client_operation(
                "pg_restore",
                url,
                container,
                [
                    f"--dbname={url.database}",
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                    "--no-privileges",
                ],
                backup.read_bytes(),
            )
            phase("restore_validation")
            async with engine.begin() as connection:
                await set_scope(connection, schema)
                inventory_after = await connection.run_sync(
                    lambda conn: schema_inventory(conn, ALL_TABLES)
                )
                rows_after = await connection.run_sync(snapshot)
                if rows_after != rows_before or inventory_after != inventory_before:
                    raise RuntimeError("Backup restore did not reproduce schema and data")
                await connection.run_sync(
                    lambda conn: tracking_round_trip(
                        conn, checked_config(conn, schema_inventory(conn), schema)
                    )
                )
            report["checks"].update(backup_restore="passed", restored_tracking_round_trip="passed")
        phase("source_verification")
        if source_identity()["inputs_sha256"] != report["source"]["inputs_sha256"]:
            raise RuntimeError("Rehearsal source changed during verification")
        report["checks"]["source_stable"] = "passed"
        phase("complete")
    except Exception as error:
        failure = error
        report["status"] = "failed"
        report["failure_code"] = "operation_failed"
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                    remaining = await connection.scalar(
                        text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
                        {"schema": schema},
                    )
                    if remaining:
                        raise RuntimeError("Rehearsal schema cleanup failed")
                report["checks"]["schema_cleanup"] = "passed"
        except Exception as error:
            report["checks"]["schema_cleanup"] = "failed"
            report["failure_code"] = "cleanup_failed"
            failure = error
        finally:
            await engine.dispose()
            report["duration_seconds"] = round(monotonic() - started, 3)
    if failure is not None:
        report["status"] = "failed"
        raise RehearsalFailure(report) from None
    report["status"] = "passed"
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False, encoding="utf-8"
        ) as handle:
            temporary = handle.name
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=os.environ.get("REHEARSAL_REPORT"))
    parser.add_argument(
        "--postgres-container",
        default=os.environ.get("POSTGRES_CONTAINER"),
        help="Use local Docker PostgreSQL clients from this test container",
    )
    args = parser.parse_args()
    try:
        report = await run_rehearsal(
            os.environ.get("TEST_DATABASE_URL"), container=args.postgres_container
        )
    except RehearsalFailure as error:
        report = error.report
    except ValueError as error:
        report = {
            "format_version": "1.0",
            "milestone": "S4.1",
            "status": "failed",
            "phase": "configuration",
            "failure_code": "invalid_database_url",
            "message": str(error),
        }
    if args.report:
        write_report(args.report, report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
