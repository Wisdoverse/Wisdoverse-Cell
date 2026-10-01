"""Candidate cutover checks without external infrastructure."""

import asyncio
import json
import sys
import time

import pytest
from alembic import command
from sqlalchemy import create_engine, text

import scripts.dev_migration_rehearsal as rehearsal_module
from agents.dev_agent.migrations.contracts import (
    canonical_check,
    schema_inventory,
    verify_inherited_schema,
    verify_scope,
)
from scripts.dev_migration_rehearsal import (
    candidate_config,
    checked_config,
    client_operation,
    fresh_round_trip,
    inherited_fixture,
    parse_database_url,
    postgres_client,
    rehearse,
    write_report,
)


@pytest.mark.public
def test_dev_cutover_round_trip_and_inherited_state_preservation():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        result = rehearse(connection)
        assert result["legacy_version_preserved"] == "passed"
        assert connection.scalar(text("SELECT status FROM dev_agent_event_outbox")) == "pending"
        assert connection.scalar(text("SELECT attempts FROM dev_agent_event_outbox")) == 0
    engine.dispose()


@pytest.mark.public
def test_rehearsal_refuses_occupied_schema_without_changes():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE existing_data (id INTEGER)"))
        with pytest.raises(RuntimeError, match="empty isolated schema"):
            rehearse(connection)
        assert connection.scalar(text("SELECT COUNT(*) FROM existing_data")) == 0
    engine.dispose()


@pytest.mark.public
def test_candidate_cli_cannot_use_runtime_database_settings():
    config = candidate_config(None)
    with pytest.raises(RuntimeError, match="rehearsal-only"):
        command.upgrade(config, "head")


@pytest.mark.public
@pytest.mark.parametrize("drift", ["missing_table", "missing_index", "extra_column"])
def test_inherited_schema_verification_rejects_drift(drift):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        fresh_round_trip(connection)
        inherited_fixture(connection)
        expected = schema_inventory(connection)
        if drift == "missing_table":
            connection.execute(text("DROP TABLE dev_agent_workflow_logs"))
        elif drift == "missing_index":
            connection.execute(text("DROP INDEX idx_dev_tasks_workflow_id"))
        else:
            connection.execute(
                text(
                    "ALTER TABLE dev_agent_event_outbox ADD COLUMN drift_probe VARCHAR DEFAULT 'x'"
                )
            )
        with pytest.raises(RuntimeError, match="incomplete|drift detected"):
            verify_inherited_schema(connection, expected)
    engine.dispose()


@pytest.mark.public
def test_canonical_check_normalizes_only_known_postgres_text_casts():
    original = "risk_level::text = ANY (ARRAY['LOW'::character varying, 'HIGH'::character varying]::text[])"
    restored = "risk_level::text = ANY (ARRAY['LOW'::character varying::text, 'HIGH'::character varying::text])"
    changed = "risk_level::text = ANY (ARRAY['LOW'::character varying, 'CRITICAL'::character varying]::text[])"
    integer_expression = "count(id)::integer > 0"

    assert canonical_check(original) == canonical_check(restored)
    assert canonical_check(original) != canonical_check(changed)
    assert canonical_check(integer_expression) == integer_expression


@pytest.mark.public
def test_checked_stamp_rejects_drift_before_version_mutation():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        fresh = fresh_round_trip(connection)
        inherited_fixture(connection)
        config = checked_config(connection, fresh)
        connection.execute(text("DROP INDEX idx_dev_tasks_workflow_id"))
        with pytest.raises(RuntimeError, match="drift detected"):
            command.stamp(config, "head")
        assert not connection.dialect.has_table(connection, "alembic_version_dev_agent")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "legacy_head_sentinel"
        )
    engine.dispose()


@pytest.mark.public
def test_inherited_baseline_destructive_downgrade_is_refused():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        fresh_round_trip(connection)
        inherited_fixture(connection)
        config = checked_config(connection, schema_inventory(connection))
        command.stamp(config, "head")
        before = set(connection.dialect.get_table_names(connection))
        with pytest.raises(RuntimeError, match="restricted to the fresh-schema rehearsal"):
            command.downgrade(config, "base")
        assert set(connection.dialect.get_table_names(connection)) == before
    engine.dispose()


@pytest.mark.public
def test_verify_scope_requires_caller_owned_transaction():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        with pytest.raises(RuntimeError, match="caller-owned transaction"):
            verify_scope(candidate_config(connection), connection)
    engine.dispose()


@pytest.mark.public
def test_invalid_database_url_error_does_not_echo_secret():
    secret = "sample-secret-should-not-appear"
    with pytest.raises(ValueError) as error:
        parse_database_url(f"postgresql+asyncpg://user:{secret}@db.example:invalid/db")
    assert secret not in str(error.value)


@pytest.mark.public
def test_postgres_client_uses_environment_credentials_and_clears_libpq_overrides(monkeypatch):
    monkeypatch.setenv("PGOPTIONS", "--search_path=public")
    monkeypatch.setenv("PGSERVICE", "unexpected-service")
    monkeypatch.setenv("PGSERVICEFILE", "/tmp/unexpected-service.conf")
    url = parse_database_url("postgresql+asyncpg://test-user:sample-secret@db.example/test-db")
    args, env = postgres_client("pg_dump", url, None)
    assert args == ["pg_dump"]
    assert "sample-secret" not in " ".join(args)
    assert env["PGPASSWORD"] == "sample-secret"
    assert not {"PGOPTIONS", "PGSERVICE", "PGSERVICEFILE"}.intersection(env)


@pytest.mark.public
def test_write_report_replaces_file_with_machine_readable_json(tmp_path):
    destination = tmp_path / "nested" / "report.json"
    write_report(destination, {"status": "passed", "checks": {"round_trip": "passed"}})
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "status": "passed",
        "checks": {"round_trip": "passed"},
    }
    assert list(destination.parent.iterdir()) == [destination]


@pytest.mark.public
def test_client_operation_terminates_timed_out_subprocess(monkeypatch):
    monkeypatch.setattr(rehearsal_module, "TOOL_TIMEOUT_SECONDS", 0.05)
    url = parse_database_url("postgresql+asyncpg://test-user:secret@db.example/test-db")
    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(
            client_operation(
                sys.executable,
                url,
                None,
                ["-c", "import time; time.sleep(30)"],
            )
        )
    assert time.monotonic() - started < 3
