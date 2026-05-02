"""Add shared control-plane ledger tables.

Revision ID: 20260501_control_plane_ledger
Revises:
Create Date: 2026-05-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260501_control_plane_ledger"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_plane_companies",
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("mission", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("company_id"),
    )

    op.create_table(
        "control_plane_goals",
        sa.Column("goal_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parent_goal_id", sa.String(length=48), nullable=True),
        sa.Column("owner_agent_id", sa.String(length=64), nullable=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("success_metric", sa.Text(), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["parent_goal_id"], ["control_plane_goals.goal_id"]),
        sa.PrimaryKeyConstraint("goal_id"),
    )
    op.create_index("ix_control_plane_goals_company_id", "control_plane_goals", ["company_id"])
    op.create_index("ix_control_plane_goals_created_at", "control_plane_goals", ["created_at"])
    op.create_index("ix_control_plane_goals_owner_agent_id", "control_plane_goals", ["owner_agent_id"])
    op.create_index("ix_control_plane_goals_owner_user_id", "control_plane_goals", ["owner_user_id"])
    op.create_index("ix_control_plane_goals_status", "control_plane_goals", ["status"])
    op.create_index(
        "ix_control_goals_company_status_created",
        "control_plane_goals",
        ["company_id", "status", "created_at"],
    )

    op.create_table(
        "control_plane_agent_roles",
        sa.Column("role_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("reports_to_agent_id", sa.String(length=64), nullable=True),
        sa.Column("adapter_type", sa.String(length=64), nullable=False),
        sa.Column("adapter_config", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("responsibilities", sa.JSON(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("budget_policy_id", sa.String(length=48), nullable=True),
        sa.Column("escalation_policy", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.PrimaryKeyConstraint("role_id"),
        sa.UniqueConstraint("company_id", "agent_id", name="uq_control_agent_role_company_agent"),
    )
    op.create_index("ix_control_plane_agent_roles_agent_id", "control_plane_agent_roles", ["agent_id"])
    op.create_index("ix_control_plane_agent_roles_adapter_type", "control_plane_agent_roles", ["adapter_type"])
    op.create_index("ix_control_plane_agent_roles_company_id", "control_plane_agent_roles", ["company_id"])
    op.create_index("ix_control_plane_agent_roles_domain", "control_plane_agent_roles", ["domain"])
    op.create_index("ix_control_plane_agent_roles_reports_to_agent_id", "control_plane_agent_roles", ["reports_to_agent_id"])
    op.create_index("ix_control_plane_agent_roles_role", "control_plane_agent_roles", ["role"])
    op.create_index("ix_control_plane_agent_roles_status", "control_plane_agent_roles", ["status"])

    op.create_table(
        "control_plane_work_items",
        sa.Column("work_item_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("goal_id", sa.String(length=48), nullable=True),
        sa.Column("owner_agent_id", sa.String(length=64), nullable=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_ref", sa.String(length=256), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["control_plane_goals.goal_id"]),
        sa.PrimaryKeyConstraint("work_item_id"),
        sa.UniqueConstraint("company_id", "external_ref", name="uq_control_work_company_external_ref"),
    )
    op.create_index("ix_control_plane_work_items_company_id", "control_plane_work_items", ["company_id"])
    op.create_index("ix_control_plane_work_items_created_at", "control_plane_work_items", ["created_at"])
    op.create_index("ix_control_plane_work_items_goal_id", "control_plane_work_items", ["goal_id"])
    op.create_index("ix_control_plane_work_items_owner_agent_id", "control_plane_work_items", ["owner_agent_id"])
    op.create_index("ix_control_plane_work_items_owner_user_id", "control_plane_work_items", ["owner_user_id"])
    op.create_index("ix_control_plane_work_items_status", "control_plane_work_items", ["status"])
    op.create_index(
        "ix_control_work_company_status_created",
        "control_plane_work_items",
        ["company_id", "status", "created_at"],
    )

    op.create_table(
        "control_plane_agent_runs",
        sa.Column("run_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trace_id", sa.String(length=96), nullable=True),
        sa.Column("goal_id", sa.String(length=48), nullable=True),
        sa.Column("work_item_id", sa.String(length=48), nullable=True),
        sa.Column("trigger_event_id", sa.String(length=48), nullable=True),
        sa.Column("input_event", sa.JSON(), nullable=True),
        sa.Column("output_events", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_successful_step", sa.String(length=128), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["control_plane_goals.goal_id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["control_plane_work_items.work_item_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_control_plane_agent_runs_agent_id", "control_plane_agent_runs", ["agent_id"])
    op.create_index("ix_control_plane_agent_runs_company_id", "control_plane_agent_runs", ["company_id"])
    op.create_index("ix_control_plane_agent_runs_started_at", "control_plane_agent_runs", ["started_at"])
    op.create_index("ix_control_plane_agent_runs_status", "control_plane_agent_runs", ["status"])
    op.create_index("ix_control_plane_agent_runs_trace_id", "control_plane_agent_runs", ["trace_id"])
    op.create_index("ix_control_plane_agent_runs_trigger_event_id", "control_plane_agent_runs", ["trigger_event_id"])
    op.create_index("ix_control_plane_agent_runs_work_item_id", "control_plane_agent_runs", ["work_item_id"])
    op.create_index("ix_control_runs_agent_started", "control_plane_agent_runs", ["agent_id", "started_at"])
    op.create_index(
        "ix_control_runs_company_status_started",
        "control_plane_agent_runs",
        ["company_id", "status", "started_at"],
    )

    op.create_table(
        "control_plane_decisions",
        sa.Column("decision_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=48), nullable=True),
        sa.Column("work_item_id", sa.String(length=48), nullable=True),
        sa.Column("goal_id", sa.String(length=48), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("selected_option", sa.String(length=128), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["control_plane_goals.goal_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["control_plane_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["control_plane_work_items.work_item_id"]),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index("ix_control_plane_decisions_company_id", "control_plane_decisions", ["company_id"])
    op.create_index("ix_control_plane_decisions_created_at", "control_plane_decisions", ["created_at"])
    op.create_index("ix_control_plane_decisions_run_id", "control_plane_decisions", ["run_id"])
    op.create_index("ix_control_plane_decisions_status", "control_plane_decisions", ["status"])

    op.create_table(
        "control_plane_approval_requests",
        sa.Column("approval_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("source_agent_id", sa.String(length=64), nullable=False),
        sa.Column("proposed_action", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("rollback_note", sa.Text(), nullable=False),
        sa.Column("affected_resources", sa.JSON(), nullable=False),
        sa.Column("artifact_links", sa.JSON(), nullable=False),
        sa.Column("run_id", sa.String(length=48), nullable=True),
        sa.Column("work_item_id", sa.String(length=48), nullable=True),
        sa.Column("goal_id", sa.String(length=48), nullable=True),
        sa.Column("trace_id", sa.String(length=96), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["control_plane_goals.goal_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["control_plane_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["control_plane_work_items.work_item_id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_control_plane_approval_requests_category", "control_plane_approval_requests", ["category"])
    op.create_index("ix_control_plane_approval_requests_company_id", "control_plane_approval_requests", ["company_id"])
    op.create_index("ix_control_plane_approval_requests_created_at", "control_plane_approval_requests", ["created_at"])
    op.create_index("ix_control_plane_approval_requests_source_agent_id", "control_plane_approval_requests", ["source_agent_id"])
    op.create_index("ix_control_plane_approval_requests_status", "control_plane_approval_requests", ["status"])
    op.create_index("ix_control_plane_approval_requests_trace_id", "control_plane_approval_requests", ["trace_id"])
    op.create_index(
        "ix_control_approvals_company_status_created",
        "control_plane_approval_requests",
        ["company_id", "status", "created_at"],
    )

    op.create_table(
        "control_plane_artifacts",
        sa.Column("artifact_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=48), nullable=True),
        sa.Column("work_item_id", sa.String(length=48), nullable=True),
        sa.Column("goal_id", sa.String(length=48), nullable=True),
        sa.Column("created_by_agent_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["control_plane_goals.goal_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["control_plane_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["control_plane_work_items.work_item_id"]),
        sa.PrimaryKeyConstraint("artifact_id"),
    )
    op.create_index("ix_control_plane_artifacts_artifact_type", "control_plane_artifacts", ["artifact_type"])
    op.create_index("ix_control_plane_artifacts_company_id", "control_plane_artifacts", ["company_id"])
    op.create_index("ix_control_plane_artifacts_created_at", "control_plane_artifacts", ["created_at"])
    op.create_index("ix_control_plane_artifacts_created_by_agent_id", "control_plane_artifacts", ["created_by_agent_id"])

    op.create_table(
        "control_plane_budget_policies",
        sa.Column("budget_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=True),
        sa.Column("period", sa.String(length=32), nullable=False),
        sa.Column("limit_usd", sa.Float(), nullable=False),
        sa.Column("warning_threshold", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_allowlist", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.PrimaryKeyConstraint("budget_id"),
    )
    op.create_index("ix_control_plane_budget_policies_company_id", "control_plane_budget_policies", ["company_id"])
    op.create_index("ix_control_plane_budget_policies_scope", "control_plane_budget_policies", ["scope"])
    op.create_index("ix_control_plane_budget_policies_scope_id", "control_plane_budget_policies", ["scope_id"])
    op.create_index("ix_control_plane_budget_policies_status", "control_plane_budget_policies", ["status"])
    op.create_index(
        "ix_control_budget_company_scope",
        "control_plane_budget_policies",
        ["company_id", "scope", "scope_id"],
    )

    op.create_table(
        "control_plane_budget_usage",
        sa.Column("usage_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("budget_id", sa.String(length=48), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=48), nullable=True),
        sa.Column("trace_id", sa.String(length=96), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["control_plane_budget_policies.budget_id"]),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["control_plane_agent_runs.run_id"]),
        sa.PrimaryKeyConstraint("usage_id"),
    )
    op.create_index("ix_control_plane_budget_usage_budget_id", "control_plane_budget_usage", ["budget_id"])
    op.create_index("ix_control_plane_budget_usage_company_id", "control_plane_budget_usage", ["company_id"])
    op.create_index("ix_control_plane_budget_usage_created_at", "control_plane_budget_usage", ["created_at"])
    op.create_index("ix_control_plane_budget_usage_trace_id", "control_plane_budget_usage", ["trace_id"])
    op.create_index(
        "ix_control_budget_usage_budget_created",
        "control_plane_budget_usage",
        ["budget_id", "created_at"],
    )

    op.create_table(
        "control_plane_audit_events",
        sa.Column("audit_event_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=96), nullable=True),
        sa.Column("run_id", sa.String(length=48), nullable=True),
        sa.Column("work_item_id", sa.String(length=48), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["control_plane_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["control_plane_work_items.work_item_id"]),
        sa.PrimaryKeyConstraint("audit_event_id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_control_audit_idempotency"),
    )
    op.create_index("ix_control_plane_audit_events_action", "control_plane_audit_events", ["action"])
    op.create_index("ix_control_plane_audit_events_company_id", "control_plane_audit_events", ["company_id"])
    op.create_index("ix_control_plane_audit_events_created_at", "control_plane_audit_events", ["created_at"])
    op.create_index("ix_control_plane_audit_events_target_id", "control_plane_audit_events", ["target_id"])
    op.create_index("ix_control_plane_audit_events_target_type", "control_plane_audit_events", ["target_type"])
    op.create_index("ix_control_plane_audit_events_trace_id", "control_plane_audit_events", ["trace_id"])
    op.create_index(
        "ix_control_audit_company_created",
        "control_plane_audit_events",
        ["company_id", "created_at"],
    )
    op.create_index("ix_control_audit_target", "control_plane_audit_events", ["target_type", "target_id"])

    op.create_table(
        "control_plane_evolution_proposals",
        sa.Column("proposal_id", sa.String(length=48), nullable=False),
        sa.Column("company_id", sa.String(length=48), nullable=False),
        sa.Column("tier", sa.String(length=8), nullable=False),
        sa.Column("scope", sa.String(length=256), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("expected_benefit", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("approval_state", sa.String(length=32), nullable=False),
        sa.Column("rollout_state", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=48), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["control_plane_approval_requests.approval_id"]),
        sa.ForeignKeyConstraint(["company_id"], ["control_plane_companies.company_id"]),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index("ix_control_plane_evolution_proposals_approval_state", "control_plane_evolution_proposals", ["approval_state"])
    op.create_index("ix_control_plane_evolution_proposals_company_id", "control_plane_evolution_proposals", ["company_id"])
    op.create_index("ix_control_plane_evolution_proposals_created_at", "control_plane_evolution_proposals", ["created_at"])
    op.create_index("ix_control_plane_evolution_proposals_rollout_state", "control_plane_evolution_proposals", ["rollout_state"])
    op.create_index("ix_control_plane_evolution_proposals_tier", "control_plane_evolution_proposals", ["tier"])


def downgrade() -> None:
    op.drop_index("ix_control_plane_evolution_proposals_tier", table_name="control_plane_evolution_proposals")
    op.drop_index("ix_control_plane_evolution_proposals_rollout_state", table_name="control_plane_evolution_proposals")
    op.drop_index("ix_control_plane_evolution_proposals_created_at", table_name="control_plane_evolution_proposals")
    op.drop_index("ix_control_plane_evolution_proposals_company_id", table_name="control_plane_evolution_proposals")
    op.drop_index("ix_control_plane_evolution_proposals_approval_state", table_name="control_plane_evolution_proposals")
    op.drop_table("control_plane_evolution_proposals")
    op.drop_index("ix_control_audit_target", table_name="control_plane_audit_events")
    op.drop_index("ix_control_audit_company_created", table_name="control_plane_audit_events")
    op.drop_index("ix_control_plane_audit_events_trace_id", table_name="control_plane_audit_events")
    op.drop_index("ix_control_plane_audit_events_target_type", table_name="control_plane_audit_events")
    op.drop_index("ix_control_plane_audit_events_target_id", table_name="control_plane_audit_events")
    op.drop_index("ix_control_plane_audit_events_created_at", table_name="control_plane_audit_events")
    op.drop_index("ix_control_plane_audit_events_company_id", table_name="control_plane_audit_events")
    op.drop_index("ix_control_plane_audit_events_action", table_name="control_plane_audit_events")
    op.drop_table("control_plane_audit_events")
    op.drop_index("ix_control_budget_usage_budget_created", table_name="control_plane_budget_usage")
    op.drop_index("ix_control_plane_budget_usage_trace_id", table_name="control_plane_budget_usage")
    op.drop_index("ix_control_plane_budget_usage_created_at", table_name="control_plane_budget_usage")
    op.drop_index("ix_control_plane_budget_usage_company_id", table_name="control_plane_budget_usage")
    op.drop_index("ix_control_plane_budget_usage_budget_id", table_name="control_plane_budget_usage")
    op.drop_table("control_plane_budget_usage")
    op.drop_index("ix_control_budget_company_scope", table_name="control_plane_budget_policies")
    op.drop_index("ix_control_plane_budget_policies_status", table_name="control_plane_budget_policies")
    op.drop_index("ix_control_plane_budget_policies_scope_id", table_name="control_plane_budget_policies")
    op.drop_index("ix_control_plane_budget_policies_scope", table_name="control_plane_budget_policies")
    op.drop_index("ix_control_plane_budget_policies_company_id", table_name="control_plane_budget_policies")
    op.drop_table("control_plane_budget_policies")
    op.drop_index("ix_control_plane_artifacts_created_by_agent_id", table_name="control_plane_artifacts")
    op.drop_index("ix_control_plane_artifacts_created_at", table_name="control_plane_artifacts")
    op.drop_index("ix_control_plane_artifacts_company_id", table_name="control_plane_artifacts")
    op.drop_index("ix_control_plane_artifacts_artifact_type", table_name="control_plane_artifacts")
    op.drop_table("control_plane_artifacts")
    op.drop_index("ix_control_approvals_company_status_created", table_name="control_plane_approval_requests")
    op.drop_index("ix_control_plane_approval_requests_trace_id", table_name="control_plane_approval_requests")
    op.drop_index("ix_control_plane_approval_requests_status", table_name="control_plane_approval_requests")
    op.drop_index("ix_control_plane_approval_requests_source_agent_id", table_name="control_plane_approval_requests")
    op.drop_index("ix_control_plane_approval_requests_created_at", table_name="control_plane_approval_requests")
    op.drop_index("ix_control_plane_approval_requests_company_id", table_name="control_plane_approval_requests")
    op.drop_index("ix_control_plane_approval_requests_category", table_name="control_plane_approval_requests")
    op.drop_table("control_plane_approval_requests")
    op.drop_index("ix_control_plane_decisions_status", table_name="control_plane_decisions")
    op.drop_index("ix_control_plane_decisions_run_id", table_name="control_plane_decisions")
    op.drop_index("ix_control_plane_decisions_created_at", table_name="control_plane_decisions")
    op.drop_index("ix_control_plane_decisions_company_id", table_name="control_plane_decisions")
    op.drop_table("control_plane_decisions")
    op.drop_index("ix_control_runs_company_status_started", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_runs_agent_started", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_work_item_id", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_trigger_event_id", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_trace_id", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_status", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_started_at", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_company_id", table_name="control_plane_agent_runs")
    op.drop_index("ix_control_plane_agent_runs_agent_id", table_name="control_plane_agent_runs")
    op.drop_table("control_plane_agent_runs")
    op.drop_index("ix_control_work_company_status_created", table_name="control_plane_work_items")
    op.drop_index("ix_control_plane_work_items_status", table_name="control_plane_work_items")
    op.drop_index("ix_control_plane_work_items_owner_user_id", table_name="control_plane_work_items")
    op.drop_index("ix_control_plane_work_items_owner_agent_id", table_name="control_plane_work_items")
    op.drop_index("ix_control_plane_work_items_goal_id", table_name="control_plane_work_items")
    op.drop_index("ix_control_plane_work_items_created_at", table_name="control_plane_work_items")
    op.drop_index("ix_control_plane_work_items_company_id", table_name="control_plane_work_items")
    op.drop_table("control_plane_work_items")
    op.drop_index("ix_control_plane_agent_roles_status", table_name="control_plane_agent_roles")
    op.drop_index("ix_control_plane_agent_roles_role", table_name="control_plane_agent_roles")
    op.drop_index("ix_control_plane_agent_roles_reports_to_agent_id", table_name="control_plane_agent_roles")
    op.drop_index("ix_control_plane_agent_roles_domain", table_name="control_plane_agent_roles")
    op.drop_index("ix_control_plane_agent_roles_company_id", table_name="control_plane_agent_roles")
    op.drop_index("ix_control_plane_agent_roles_adapter_type", table_name="control_plane_agent_roles")
    op.drop_index("ix_control_plane_agent_roles_agent_id", table_name="control_plane_agent_roles")
    op.drop_table("control_plane_agent_roles")
    op.drop_index("ix_control_goals_company_status_created", table_name="control_plane_goals")
    op.drop_index("ix_control_plane_goals_status", table_name="control_plane_goals")
    op.drop_index("ix_control_plane_goals_owner_user_id", table_name="control_plane_goals")
    op.drop_index("ix_control_plane_goals_owner_agent_id", table_name="control_plane_goals")
    op.drop_index("ix_control_plane_goals_created_at", table_name="control_plane_goals")
    op.drop_index("ix_control_plane_goals_company_id", table_name="control_plane_goals")
    op.drop_table("control_plane_goals")
    op.drop_table("control_plane_companies")
