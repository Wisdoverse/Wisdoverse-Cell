"""Add requirement manager tables.

Revision ID: 20260502_reqmgr_tables
Revises: 20260501_control_plane_ledger
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_reqmgr_tables"
down_revision: str | None = "20260501_control_plane_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=False),
        sa.Column("sender_name", sa.String(length=128), nullable=True),
        sa.Column("message_type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(length=32), nullable=True),
        sa.Column("requirement_ids", sa.JSON(), nullable=False),
        sa.Column("extracted", sa.Boolean(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index("ix_chat_messages_chat_session", "chat_messages", ["chat_id", "session_id"])
    op.create_index("ix_chat_messages_extracted", "chat_messages", ["extracted"])
    op.create_index("ix_chat_messages_sent_at", "chat_messages", ["sent_at"])

    op.create_table(
        "feedback_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=True),
        sa.Column("original_title", sa.Text(), nullable=False),
        sa.Column("original_description", sa.Text(), nullable=True),
        sa.Column("original_priority", sa.String(length=20), nullable=True),
        sa.Column("original_category", sa.String(length=50), nullable=True),
        sa.Column("corrected_title", sa.Text(), nullable=False),
        sa.Column("corrected_description", sa.Text(), nullable=True),
        sa.Column("corrected_priority", sa.String(length=20), nullable=True),
        sa.Column("corrected_category", sa.String(length=50), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("feedback_type", sa.String(length=20), nullable=False),
        sa.Column("corrected_by", sa.String(length=100), nullable=False),
        sa.Column("correction_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("used_in_prompt", sa.Boolean(), nullable=False),
        sa.Column("effectiveness_score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_records_requirement_id", "feedback_records", ["requirement_id"])

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("agent_id", sa.String(length=50), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_agent_date", "llm_usage", ["agent_id", "created_at"])
    op.create_index("ix_llm_usage_agent_id", "llm_usage", ["agent_id"])
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])
    op.create_index("ix_llm_usage_date_success", "llm_usage", ["created_at", "success"])
    op.create_index("ix_llm_usage_task_type", "llm_usage", ["task_type"])
    op.create_index("ix_llm_usage_trace_id", "llm_usage", ["trace_id"])

    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("meeting_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "requirements",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("source_meeting_ids", sa.JSON(), nullable=False),
        sa.Column("context_message_ids", sa.JSON(), nullable=False),
        sa.Column("confirmed_by", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "open_questions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("requirement_id", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_by", sa.String(length=64), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("open_questions")
    op.drop_table("requirements")
    op.drop_table("meetings")
    op.drop_table("llm_usage")
    op.drop_table("feedback_records")
    op.drop_table("chat_messages")
