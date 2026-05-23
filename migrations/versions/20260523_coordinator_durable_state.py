"""Add coordinator durable state tables (DDD-018, ADR-0008).

Revision ID: 20260523_coordinator_durable_state
Revises: 20260517_qa_acceptance_runs_defaults
Create Date: 2026-05-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260523_coordinator_durable_state"
down_revision: str | None = "20260517_qa_acceptance_runs_defaults"
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
    if not _table_exists("coordinator_agent_state"):
        op.create_table(
            "coordinator_agent_state",
            sa.Column("agent_id", sa.String(length=64), primary_key=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("current_task", sa.String(length=64), nullable=True),
            sa.Column("last_output_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_coordinator_agent_state_status",
            "coordinator_agent_state",
            ["status"],
        )

    if not _table_exists("coordinator_workflow_state"):
        op.create_table(
            "coordinator_workflow_state",
            sa.Column("workflow_id", sa.String(length=64), primary_key=True),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("current_phase", sa.String(length=64), nullable=False),
            sa.Column("agents_involved", _jsonb_or_json(), nullable=False),
            sa.Column("context", _jsonb_or_json(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_coordinator_workflow_state_status",
            "coordinator_workflow_state",
            ["status"],
        )

    if not _table_exists("coordinator_pending_decision"):
        op.create_table(
            "coordinator_pending_decision",
            sa.Column("decision_id", sa.String(length=32), primary_key=True),
            sa.Column("workflow_id", sa.String(length=64), nullable=True),
            sa.Column("reasoning", sa.Text(), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_agent", sa.String(length=64), nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=True),
            sa.Column("outcome", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index(
            "ix_coordinator_pending_decision_workflow_id",
            "coordinator_pending_decision",
            ["workflow_id"],
        )
        op.create_index(
            "ix_coordinator_pending_decision_target_agent",
            "coordinator_pending_decision",
            ["target_agent"],
        )
        op.create_index(
            "ix_coordinator_pending_decision_created_at",
            "coordinator_pending_decision",
            ["created_at"],
        )


def downgrade() -> None:
    if _table_exists("coordinator_pending_decision"):
        _drop_index_if_exists(
            "ix_coordinator_pending_decision_created_at",
            "coordinator_pending_decision",
        )
        _drop_index_if_exists(
            "ix_coordinator_pending_decision_target_agent",
            "coordinator_pending_decision",
        )
        _drop_index_if_exists(
            "ix_coordinator_pending_decision_workflow_id",
            "coordinator_pending_decision",
        )
        op.drop_table("coordinator_pending_decision")

    if _table_exists("coordinator_workflow_state"):
        _drop_index_if_exists(
            "ix_coordinator_workflow_state_status",
            "coordinator_workflow_state",
        )
        op.drop_table("coordinator_workflow_state")

    if _table_exists("coordinator_agent_state"):
        _drop_index_if_exists(
            "ix_coordinator_agent_state_status",
            "coordinator_agent_state",
        )
        op.drop_table("coordinator_agent_state")
