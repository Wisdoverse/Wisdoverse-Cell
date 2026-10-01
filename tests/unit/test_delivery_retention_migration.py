"""DDL parity and durable-data downgrade guards for delivery/retention migration."""

from datetime import UTC, datetime
from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

migration = import_module("migrations.versions.20261001_delivery_retention")

_TABLES = (
    "requirement_delivery_handoffs",
    "control_plane_audit_retention_tombstones",
    "control_plane_retention_runs",
)


@pytest.fixture
def migrated_connection(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        yield connection
    engine.dispose()


def test_upgrade_creates_owned_tables_indexes_and_model_column_parity(migrated_connection):
    connection = migrated_connection
    inspector = inspect(connection)
    assert set(inspector.get_table_names()) == set(_TABLES)

    expected_models = {
        "requirement_delivery_handoffs": import_module(
            "agents.requirement_manager.db.delivery_handoff"
        ).RequirementDeliveryHandoffTable.__table__,
    }
    control_plane_models = import_module("shared.control_plane.retention_models")
    expected_models.update({
        "control_plane_audit_retention_tombstones": (
            control_plane_models.AuditRetentionTombstoneTable.__table__
        ),
        "control_plane_retention_runs": control_plane_models.RetentionRunTable.__table__,
    })
    for table_name, model_table in expected_models.items():
        actual = inspector.get_columns(table_name)
        assert [(column["name"], str(column["type"]), column["nullable"])
                for column in actual] == [
            (column.name, str(column.type), column.nullable) for column in model_table.columns
        ]
        assert inspector.get_pk_constraint(table_name)["constrained_columns"] == [
            column.name for column in model_table.primary_key.columns
        ]
        actual_fks = sorted(
            (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
            for fk in inspector.get_foreign_keys(table_name)
        )
        expected_fks = sorted(
            (
                (foreign_key.parent.name,),
                foreign_key.column.table.name,
                (foreign_key.column.name,),
            )
            for foreign_key in model_table.foreign_keys
        )
        assert actual_fks == expected_fks

    handoff_indexes = {index["name"]: index for index in inspector.get_indexes(_TABLES[0])}
    assert handoff_indexes["ix_requirement_delivery_handoffs_company_id"]["column_names"] == [
        "company_id"
    ]
    handoff_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints(_TABLES[0])
    }
    assert handoff_constraints["uq_requirement_delivery_wp"]["column_names"] == [
        "company_id",
        "project_id",
        "wp_id",
    ]
    tombstone_indexes = {index["name"]: index for index in inspector.get_indexes(_TABLES[1])}
    assert tombstone_indexes["ix_control_plane_audit_retention_tombstones_company_id"][
        "column_names"
    ] == ["company_id"]
    assert tombstone_indexes["uq_control_audit_retention_key"]["unique"] == 1
    assert tombstone_indexes["uq_control_audit_retention_key"]["column_names"] == [
        "company_id",
        "idempotency_hash",
    ]

    migration.downgrade()
    assert inspect(connection).get_table_names() == []
    migration.upgrade()
    assert set(inspect(connection).get_table_names()) == set(_TABLES)


@pytest.mark.parametrize("table_name", _TABLES)
def test_downgrade_refuses_each_nonempty_durable_table_without_dropping_any(
    migrated_connection, table_name
):
    now = datetime.now(UTC)
    if table_name == "requirement_delivery_handoffs":
        migrated_connection.execute(
            text(
                "INSERT INTO requirement_delivery_handoffs "
                "(requirement_id, company_id, project_id, wp_id, receipt, created_at) "
                "VALUES (:id, :company, :project, :wp, :receipt, :now)"
            ),
            {
                "id": "req_retention_test",
                "company": "cmp_test",
                "project": 1,
                "wp": 2,
                "receipt": "{}",
                "now": now,
            },
        )
    elif table_name == "control_plane_audit_retention_tombstones":
        migrated_connection.execute(
            text(
                "INSERT INTO control_plane_audit_retention_tombstones "
                "(audit_event_id, company_id, idempotency_hash, receipt, purged_at) "
                "VALUES (:id, :company, :hash, :receipt, :now)"
            ),
            {
                "id": "audit_retention_test",
                "company": "cmp_test",
                "hash": "a" * 64,
                "receipt": "{}",
                "now": now,
            },
        )
    else:
        migrated_connection.execute(
            text(
                "INSERT INTO control_plane_retention_runs "
                "(company_id, request_id, command_hash, receipt, created_at) "
                "VALUES (:company, :request, :hash, :receipt, :now)"
            ),
            {
                "company": "cmp_test",
                "request": "retention_request",
                "hash": "b" * 64,
                "receipt": "{}",
                "now": now,
            },
        )

    with pytest.raises(RuntimeError, match="requires empty durable receipt tables"):
        migration.downgrade()
    assert set(inspect(migrated_connection).get_table_names()) == set(_TABLES)
    assert migrated_connection.scalar(text(f'SELECT COUNT(*) FROM "{table_name}"')) == 1
