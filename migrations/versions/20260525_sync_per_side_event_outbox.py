"""Add per-side Sync event outbox tables (DDD-014 / ADR-0009 Step 1).

Revision ID: 20260525_sync_per_side_event_outbox
Revises: 20260524_analysis_projection_tables
Create Date: 2026-05-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260525_sync_per_side_event_outbox"
down_revision: str | None = "20260524_analysis_projection_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _jsonb_or_json() -> sa.TypeEngine:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _outbox_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("event_id", sa.String(length=32), primary_key=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("source_agent", sa.String(length=64), nullable=False),
        sa.Column("payload", _jsonb_or_json(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(f"ix_{name}_event_type", name, ["event_type"])
    op.create_index(f"ix_{name}_status", name, ["status"])


def upgrade() -> None:
    if not _table_exists("sync_openproject_event_outbox"):
        _outbox_table("sync_openproject_event_outbox")
    if not _table_exists("sync_feishu_bitable_event_outbox"):
        _outbox_table("sync_feishu_bitable_event_outbox")


def downgrade() -> None:
    for table in ("sync_feishu_bitable_event_outbox", "sync_openproject_event_outbox"):
        if _table_exists(table):
            _drop_index_if_exists(f"ix_{table}_status", table)
            _drop_index_if_exists(f"ix_{table}_event_type", table)
            op.drop_table(table)
