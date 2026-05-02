"""Clean-database migration smoke test for the control-plane ledger."""

from importlib import import_module
from unittest.mock import patch

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect


def test_control_plane_migration_upgrades_clean_database():
    migration = import_module("migrations.versions.20260501_control_plane_ledger")
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        with patch.object(migration, "op", operations):
            migration.upgrade()

        tables = set(inspect(connection).get_table_names())

    assert {
        "control_plane_companies",
        "control_plane_goals",
        "control_plane_agent_roles",
        "control_plane_agent_runs",
        "control_plane_approval_requests",
        "control_plane_budget_usage",
        "control_plane_audit_events",
    }.issubset(tables)
