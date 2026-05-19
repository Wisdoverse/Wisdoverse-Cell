"""Align qa_acceptance_runs server defaults with the SQLAlchemy model.

Revision ID: 20260517_qa_acceptance_runs_defaults
Revises: 20260516_evolution_event_outbox
Create Date: 2026-05-19

`qa_acceptance_runs.files_changed` and `notification_summary` are NOT NULL
in the schema but lack server defaults, while the SQLAlchemy model declares
`server_default="[]"` and `server_default="{}"`. ORM `server_default` only
fires when the column is in the insert value list, so inserts that omit the
columns hit NotNullViolation.

This migration adds the missing server defaults so any client (test,
inbound HTTP, replay) that omits these columns gets an empty JSON literal.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260517_qa_acceptance_runs_defaults"
down_revision: str | None = "20260516_evolution_event_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLUMN_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("files_changed", "'[]'::jsonb"),
    ("notification_summary", "'{}'::jsonb"),
)


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _table_exists("qa_acceptance_runs"):
        return
    for column, default_sql in _COLUMN_DEFAULTS:
        op.alter_column(
            "qa_acceptance_runs",
            column,
            server_default=sa.text(default_sql),
            existing_type=postgresql.JSONB(),
            existing_nullable=False,
        )


def downgrade() -> None:
    if not _table_exists("qa_acceptance_runs"):
        return
    for column, _ in _COLUMN_DEFAULTS:
        op.alter_column(
            "qa_acceptance_runs",
            column,
            server_default=None,
            existing_type=postgresql.JSONB(),
            existing_nullable=False,
        )
