"""Static receiver DDL parity and nonempty-ledger downgrade guard."""

from datetime import UTC, datetime
from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

migration = import_module("migrations.versions.20261001_native_executor_receipts")


@pytest.fixture
def migrated_connection(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        yield connection
    engine.dispose()


def test_native_receipt_migration_round_trip_and_owner_metadata_parity(migrated_connection):
    connection = migrated_connection
    expected = {
        "requirement_manager": "requirement_manager_executor_requests",
        "pjm_agent": "pjm_executor_requests",
        "dev_agent": "dev_agent_executor_requests",
        "qa_agent": "qa_executor_requests",
    }
    assert set(inspect(connection).get_table_names()) == set(expected.values())
    for owner, table_name in expected.items():
        table = import_module(f"agents.{owner}.db.executor_ledger").executor_table
        actual = inspect(connection).get_columns(table_name)
        assert [(c["name"], str(c["type"]), c["nullable"]) for c in actual] == [
            (c.name, str(c.type), c.nullable) for c in table.columns
        ]
    migration.downgrade()
    assert inspect(connection).get_table_names() == []
    migration.upgrade()
    assert set(inspect(connection).get_table_names()) == set(expected.values())


@pytest.mark.parametrize("table", migration._TABLES)
def test_native_receipt_downgrade_refuses_any_nonempty_owner_ledger(migrated_connection, table):
    now = datetime.now(UTC)
    migrated_connection.execute(
        text(
            f'INSERT INTO "{table}" (run_id, company_id, request_hash, state, created_at, updated_at) VALUES (:run, :company, :hash, :state, :now, :now)'
        ),
        {
            "run": "run-uncertain",
            "company": "cmp-migration",
            "hash": "a" * 64,
            "state": "uncertain",
            "now": now,
        },
    )
    with pytest.raises(RuntimeError, match="requires empty receipt tables"):
        migration.downgrade()
    assert set(inspect(migrated_connection).get_table_names()) == set(migration._TABLES)
    assert migrated_connection.scalar(text(f'SELECT COUNT(*) FROM "{table}"')) == 1
