"""Frozen Dev schema baseline; rehearsal only until operational cutover acceptance."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "20261001_dev_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _jsonb_or_json() -> sa.types.TypeEngine:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _create_dev_tables() -> None:
    op.create_table(
        "dev_agent_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("wp_id", sa.Integer(), nullable=False),
        sa.Column("task_title", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column("workflow_id", sa.String(), nullable=True),
        sa.Column("mr_iid", sa.Integer(), nullable=True),
        sa.Column("mr_url", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("failed_step", sa.String(length=50), nullable=True),
        sa.Column("workflow_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_dev_risk_level"
        ),
        sa.CheckConstraint(
            "status IN ('pending','planning','awaiting_approval','executing','security_scanning','mr_creating','mr_created','qa_triggered','reviewing','completed','failed','expired')",
            name="ck_dev_status",
        ),
        sa.UniqueConstraint("wp_id"),
    )
    op.create_table(
        "dev_agent_workflow_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("workflow_json", _jsonb_or_json(), nullable=True),
        sa.Column("llm_request_prompt", sa.Text(), nullable=True),
        sa.Column("llm_response_raw", sa.Text(), nullable=True),
        sa.Column("tool_routing_json", _jsonb_or_json(), nullable=True),
        sa.Column("node_results", _jsonb_or_json(), nullable=True),
        sa.Column("total_duration_s", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["dev_agent_tasks.id"]),
    )
    op.create_index("idx_dev_tasks_status", "dev_agent_tasks", ["status", "created_at"])
    op.create_index("idx_dev_tasks_workflow_id", "dev_agent_tasks", ["workflow_id"])
    op.create_index("idx_dev_tasks_mr_iid", "dev_agent_tasks", ["mr_iid"])


def _create_outbox() -> None:
    op.create_table(
        "dev_agent_event_outbox",
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dev_agent_event_outbox_event_type", "dev_agent_event_outbox", ["event_type"]
    )
    op.create_index("ix_dev_agent_event_outbox_status", "dev_agent_event_outbox", ["status"])


def upgrade() -> None:
    _create_dev_tables()
    _create_outbox()


def downgrade() -> None:
    if not context.config.attributes.get("allow_destructive_baseline"):
        raise RuntimeError("Baseline downgrade is restricted to the fresh-schema rehearsal")
    op.drop_table("dev_agent_event_outbox")
    op.drop_table("dev_agent_workflow_logs")
    op.drop_table("dev_agent_tasks")
