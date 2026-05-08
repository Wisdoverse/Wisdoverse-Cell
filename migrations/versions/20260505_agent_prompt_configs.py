"""Add durable agent prompt configuration table.

Revision ID: 20260505_agent_prompt_configs
Revises: 20260504_runtime_tables
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_agent_prompt_configs"
down_revision: str | None = "20260504_runtime_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _table_exists("control_plane_agent_prompt_configs"):
        return
    op.create_table(
        "control_plane_agent_prompt_configs",
        sa.Column(
            "company_id",
            sa.String(length=48),
            sa.ForeignKey("control_plane_companies.company_id"),
            primary_key=True,
        ),
        sa.Column("agent_id", sa.String(length=64), primary_key=True),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(length=128), nullable=False, server_default="system"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_control_prompt_configs_agent",
        "control_plane_agent_prompt_configs",
        ["agent_id"],
    )


def downgrade() -> None:
    if not _table_exists("control_plane_agent_prompt_configs"):
        return
    op.drop_index(
        "ix_control_prompt_configs_agent",
        table_name="control_plane_agent_prompt_configs",
    )
    op.drop_table("control_plane_agent_prompt_configs")
