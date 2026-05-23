"""Add analysis projection tables (DDD-004 follow-up).

Revision ID: 20260524_analysis_projection_tables
Revises: 20260523_coordinator_durable_state
Create Date: 2026-05-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260524_analysis_projection_tables"
down_revision: str | None = "20260523_coordinator_durable_state"
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


def upgrade() -> None:
    if not _table_exists("analysis_work_package_projection"):
        op.create_table(
            "analysis_work_package_projection",
            sa.Column("wp_id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("subject", sa.String(length=512), nullable=False),
            sa.Column("type_name", sa.String(length=64), nullable=True),
            sa.Column("status_name", sa.String(length=64), nullable=False),
            sa.Column(
                "percentage_done",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("assigned_to", sa.String(length=128), nullable=True),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "extra",
                _jsonb_or_json(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb")
                if op.get_bind().dialect.name == "postgresql"
                else sa.text("'{}'"),
            ),
        )
        op.create_index(
            "ix_analysis_wpp_project_id",
            "analysis_work_package_projection",
            ["project_id"],
        )
        op.create_index(
            "ix_analysis_wpp_parent_id",
            "analysis_work_package_projection",
            ["parent_id"],
        )
        op.create_index(
            "ix_analysis_wpp_updated_at",
            "analysis_work_package_projection",
            ["updated_at"],
        )

    if not _table_exists("analysis_subtask_progress_projection"):
        op.create_table(
            "analysis_subtask_progress_projection",
            sa.Column(
                "subtask_record_id", sa.String(length=64), primary_key=True
            ),
            sa.Column("parent_wp_id", sa.Integer(), nullable=False),
            sa.Column("subtask_status", sa.String(length=64), nullable=False),
            sa.Column(
                "completed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_analysis_spp_parent_wp_id",
            "analysis_subtask_progress_projection",
            ["parent_wp_id"],
        )
        op.create_index(
            "ix_analysis_spp_updated_at",
            "analysis_subtask_progress_projection",
            ["updated_at"],
        )


def downgrade() -> None:
    if _table_exists("analysis_subtask_progress_projection"):
        _drop_index_if_exists(
            "ix_analysis_spp_updated_at",
            "analysis_subtask_progress_projection",
        )
        _drop_index_if_exists(
            "ix_analysis_spp_parent_wp_id",
            "analysis_subtask_progress_projection",
        )
        op.drop_table("analysis_subtask_progress_projection")

    if _table_exists("analysis_work_package_projection"):
        _drop_index_if_exists(
            "ix_analysis_wpp_updated_at",
            "analysis_work_package_projection",
        )
        _drop_index_if_exists(
            "ix_analysis_wpp_parent_id",
            "analysis_work_package_projection",
        )
        _drop_index_if_exists(
            "ix_analysis_wpp_project_id",
            "analysis_work_package_projection",
        )
        op.drop_table("analysis_work_package_projection")
