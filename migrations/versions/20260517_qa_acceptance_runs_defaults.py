"""Align qa_acceptance_runs server defaults with the SQLAlchemy model.

Revision ID: 20260517_qa_acceptance_runs_defaults
Revises: 20260516_evolution_event_outbox
Create Date: 2026-05-19

Discovered during local E2E (post-#162): `qa_acceptance_runs.files_changed`
and `notification_summary` are NOT NULL in the schema but lack server
defaults, while the SQLAlchemy model declares `server_default="[]"` and
`server_default="{}"`. Inserts that omit the columns rely on the model
default — which the ORM only emits when the column is in the value
list.

This migration adds the missing server defaults so any client (test,
inbound HTTP, or replay) that omits these columns gets an empty JSON
literal instead of a NotNullViolation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_qa_acceptance_runs_defaults"
down_revision: str | None = "20260516_evolution_event_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _table_exists("qa_acceptance_runs"):
        return
    op.alter_column(
        "qa_acceptance_runs",
        "files_changed",
        server_default=sa.text("'[]'::jsonb"),
        existing_type=sa.dialects.postgresql.JSONB(),
        existing_nullable=False,
    )
    op.alter_column(
        "qa_acceptance_runs",
        "notification_summary",
        server_default=sa.text("'{}'::jsonb"),
        existing_type=sa.dialects.postgresql.JSONB(),
        existing_nullable=False,
    )


def downgrade() -> None:
    if not _table_exists("qa_acceptance_runs"):
        return
    op.alter_column(
        "qa_acceptance_runs",
        "files_changed",
        server_default=None,
        existing_type=sa.dialects.postgresql.JSONB(),
        existing_nullable=False,
    )
    op.alter_column(
        "qa_acceptance_runs",
        "notification_summary",
        server_default=None,
        existing_type=sa.dialects.postgresql.JSONB(),
        existing_nullable=False,
    )
