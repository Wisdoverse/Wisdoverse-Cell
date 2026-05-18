"""Add Identity/User-owned users table.

Revision ID: 20260506_identity_users_table
Revises: 20260505_agent_prompt_configs
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_identity_users_table"
down_revision: str | None = "20260505_agent_prompt_configs"
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
    if _table_exists("users"):
        return

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("feishu_open_id", sa.String(length=64), nullable=True),
        sa.Column("feishu_user_id", sa.String(length=64), nullable=True),
        sa.Column("wecom_user_id", sa.String(length=64), nullable=True),
        sa.Column("web_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_platform", sa.String(length=16), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_feishu_open_id", "users", ["feishu_open_id"], unique=True)
    op.create_index("ix_users_wecom_user_id", "users", ["wecom_user_id"], unique=True)
    op.create_index("ix_users_web_user_id", "users", ["web_user_id"], unique=True)


def downgrade() -> None:
    if not _table_exists("users"):
        return

    _drop_index_if_exists("ix_users_web_user_id", "users")
    _drop_index_if_exists("ix_users_wecom_user_id", "users")
    _drop_index_if_exists("ix_users_feishu_open_id", "users")
    _drop_index_if_exists("ix_users_phone", "users")
    _drop_index_if_exists("ix_users_email", "users")
    op.drop_table("users")
