"""Add Requirement integration event outbox.

Revision ID: 20260507_requirement_event_outbox
Revises: 20260506_identity_users_table
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260507_requirement_event_outbox"
down_revision: str | None = "20260506_identity_users_table"
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


def upgrade() -> None:
    if _table_exists("requirement_event_outbox"):
        return

    op.create_table(
        "requirement_event_outbox",
        sa.Column("event_id", sa.String(length=32), primary_key=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("source_agent", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_requirement_event_outbox_event_type",
        "requirement_event_outbox",
        ["event_type"],
    )
    op.create_index(
        "ix_requirement_event_outbox_status",
        "requirement_event_outbox",
        ["status"],
    )


def downgrade() -> None:
    if not _table_exists("requirement_event_outbox"):
        return

    _drop_index_if_exists("ix_requirement_event_outbox_status", "requirement_event_outbox")
    _drop_index_if_exists("ix_requirement_event_outbox_event_type", "requirement_event_outbox")
    op.drop_table("requirement_event_outbox")
