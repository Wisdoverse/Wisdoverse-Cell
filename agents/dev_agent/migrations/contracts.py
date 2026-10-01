"""Ownership and verification contracts for the inactive Dev migration surface."""

from __future__ import annotations

import re
from typing import Any

from alembic.config import Config
from sqlalchemy import Connection, inspect, text

OWNED_TABLES = ("dev_agent_tasks", "dev_agent_workflow_logs", "dev_agent_event_outbox")
REVISION = "20261001_dev_baseline"
VERSION_TABLE = "alembic_version_dev_agent"
SCHEMA_PREFIX = "dev_rehearsal_"


def canonical_check(expression: str) -> str:
    """Normalize dump/restore's equivalent casts for Dev's finite text vocabularies.

    PostgreSQL reparses ARRAY::text[] into per-element ::text casts on restore.
    Limit normalization to the two known text columns. Every literal,
    comparison and other expression remains significant for drift detection.
    """
    if not expression.startswith(("risk_level::text = ANY (ARRAY[", "status::text = ANY (ARRAY[")):
        return expression
    expression = re.sub(r"('(?:[^']|'')*')::character varying(?:::text)?", r"\1::text", expression)
    return expression.replace("]::text[])", "])")


def schema_inventory(
    connection: Connection, tables: tuple[str, ...] = OWNED_TABLES
) -> dict[str, Any]:
    """Compare structural DDL, including defaults and constraint/index options."""
    inspector = inspect(connection)
    return {
        table: {
            "columns": [
                (column["name"], str(column["type"]), column["nullable"], column.get("default"))
                for column in inspector.get_columns(table)
            ],
            "pk": inspector.get_pk_constraint(table),
            "indexes": sorted(inspector.get_indexes(table), key=lambda item: item["name"]),
            "unique": sorted(
                inspector.get_unique_constraints(table), key=lambda item: item["name"] or ""
            ),
            "checks": sorted(
                [
                    {**item, "sqltext": canonical_check(item["sqltext"])}
                    for item in inspector.get_check_constraints(table)
                ],
                key=lambda item: item["name"] or "",
            ),
            "fks": sorted(inspector.get_foreign_keys(table), key=lambda item: item["name"] or ""),
        }
        for table in tables
    }


def verify_scope(config: Config, connection: Connection) -> None:
    """Refuse runtime URLs, public schemas, and caller connections outside a transaction."""
    if not connection.in_transaction():
        raise RuntimeError("Rehearsal migrations require a caller-owned transaction")
    if connection.dialect.name == "sqlite" and config.attributes.get("sqlite_unit_test"):
        return
    schema = config.attributes.get("rehearsal_schema")
    if connection.dialect.name != "postgresql" or not isinstance(schema, str):
        raise RuntimeError("Dev migrations require an isolated PostgreSQL rehearsal schema")
    suffix = schema.removeprefix(SCHEMA_PREFIX)
    if (
        not schema.startswith(SCHEMA_PREFIX)
        or len(suffix) != 32
        or any(c not in "0123456789abcdef" for c in suffix)
    ):
        raise RuntimeError("Invalid rehearsal schema")
    if connection.scalar(text("SELECT current_schema()")) != schema:
        raise RuntimeError("Rehearsal connection targets the wrong schema")
    if connection.scalar(text("SHOW search_path")) != schema:
        raise RuntimeError("Rehearsal search path must exclude other schemas")


def verify_inherited_schema(connection: Connection, expected: dict[str, Any]) -> None:
    """Fail before stamping mismatched or incomplete inherited Dev tables."""
    if not set(OWNED_TABLES).issubset(inspect(connection).get_table_names()):
        raise RuntimeError("Inherited Dev schema is incomplete")
    if schema_inventory(connection) != expected:
        raise RuntimeError("Inherited Dev schema drift detected")
