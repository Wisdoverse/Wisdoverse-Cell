"""Add runtime-owned operational tables.

Revision ID: 20260504_runtime_tables
Revises: 20260504_pjm_decomp_statuses
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260504_runtime_tables"
down_revision: str | None = "20260504_pjm_decomp_statuses"
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


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str | sa.ColumnElement],
    *,
    unique: bool = False,
    postgresql_where: sa.ColumnElement[bool] | None = None,
) -> None:
    if _index_exists(table_name, index_name):
        return
    kwargs = {"unique": unique}
    if postgresql_where is not None:
        kwargs["postgresql_where"] = postgresql_where
    op.create_index(index_name, table_name, columns, **kwargs)


def _jsonb_or_json() -> sa.TypeEngine:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    _create_pjm_tables()
    _create_qa_tables()
    _create_dev_tables()
    _create_user_interaction_tables()
    _create_sync_tables()
    _create_analysis_tables()
    _create_evolution_tables()


def downgrade() -> None:
    for table_name in [
        "evolution_collaboration_patterns",
        "evolution_memory",
        "evolution_experiments",
        "evolution_reflections",
        "evolution_skill_configs",
        "evolution_traces",
        "analysis_agent_report_logs",
        "sync_agent_locks",
        "sync_agent_logs",
        "sync_agent_subtask_mappings",
        "sync_agent_mappings",
        "chat_agent_daily_progress",
        "chat_agent_card_operations",
        "chat_agent_conversation_histories",
        "dev_agent_workflow_logs",
        "dev_agent_tasks",
        "qa_acceptance_results",
        "qa_acceptance_runs",
        "pjm_agent_decomposition_records",
        "pjm_agent_config_cache",
        "pjm_agent_alert_logs",
    ]:
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table_name}"))


def _create_pjm_tables() -> None:
    if not _table_exists("pjm_agent_alert_logs"):
        op.create_table(
            "pjm_agent_alert_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("alert_type", sa.String(length=50), nullable=False),
            sa.Column("target", sa.String(length=200), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "alert_type IN ('deadline', 'overload', 'progress', 'blocked')",
                name="ck_alert_type",
            ),
            sa.CheckConstraint(
                "severity IN ('critical', 'warning', 'info')",
                name="ck_alert_severity",
            ),
        )

    if not _table_exists("pjm_agent_config_cache"):
        op.create_table(
            "pjm_agent_config_cache",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("config_type", sa.String(length=50), nullable=False),
            sa.Column("config_data", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "config_type IN ('members', 'projects', 'rules', 'workload')",
                name="ck_config_type",
            ),
            sa.UniqueConstraint("config_type"),
        )

    if not _table_exists("pjm_agent_decomposition_records"):
        op.create_table(
            "pjm_agent_decomposition_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("wp_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("assignee_id", sa.Integer(), nullable=True),
            sa.Column("decompose_result", _jsonb_or_json(), nullable=True),
            sa.Column("approved_by", sa.String(length=100), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'writing', 'approved', 'rejected', "
                "'failed', 'write_failed')",
                name="ck_decompose_status",
            ),
            sa.UniqueConstraint("wp_id"),
        )


def _create_qa_tables() -> None:
    if not _table_exists("qa_acceptance_runs"):
        op.create_table(
            "qa_acceptance_runs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("trigger_event_id", sa.String(length=64), nullable=True),
            sa.Column("agent_name", sa.String(length=100), nullable=False),
            sa.Column("target_path", sa.String(length=255), nullable=False),
            sa.Column("commit_sha", sa.String(length=40), nullable=True),
            sa.Column("branch", sa.String(length=255), nullable=True),
            sa.Column("mr_iid", sa.Integer(), nullable=True),
            sa.Column("gitlab_project_id", sa.Integer(), nullable=True),
            sa.Column("trigger", sa.String(length=20), nullable=False),
            sa.Column("level", sa.String(length=10), nullable=False),
            sa.Column("l0_status", sa.String(length=10), nullable=False),
            sa.Column("l1_status", sa.String(length=10), nullable=False),
            sa.Column("l2_status", sa.String(length=10), nullable=False),
            sa.Column("total_checks", sa.Integer(), nullable=False),
            sa.Column("l0_failure_count", sa.Integer(), nullable=False),
            sa.Column("l1_warning_count", sa.Integer(), nullable=False),
            sa.Column("duration_seconds", sa.Float(), nullable=False),
            sa.Column("runner_exit_code", sa.Integer(), nullable=False),
            sa.Column("files_changed", _jsonb_or_json(), nullable=False),
            sa.Column("raw_report", _jsonb_or_json(), nullable=False),
            sa.Column("report_markdown", sa.Text(), nullable=True),
            sa.Column("notification_summary", _jsonb_or_json(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "trigger IN ('event', 'api', 'manual', 'scheduled')",
                name="ck_qa_run_trigger",
            ),
            sa.CheckConstraint(
                "level IN ('l0', 'l1', 'l2', 'all')",
                name="ck_qa_run_level",
            ),
            sa.CheckConstraint(
                "l0_status IN ('PASS', 'FAIL', 'ERROR')",
                name="ck_qa_run_l0_status",
            ),
            sa.CheckConstraint(
                "l1_status IN ('PASS', 'WARN', 'ERROR')",
                name="ck_qa_run_l1_status",
            ),
            sa.CheckConstraint("duration_seconds >= 0", name="ck_qa_run_duration"),
        )

    if not _table_exists("qa_acceptance_results"):
        op.create_table(
            "qa_acceptance_results",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("run_id", sa.String(length=32), nullable=False),
            sa.Column("level", sa.String(length=4), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("check_name", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=10), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("is_blocking", sa.Boolean(), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("file_path", sa.String(length=255), nullable=True),
            sa.Column("line_number", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["qa_acceptance_runs.id"]),
            sa.CheckConstraint("level IN ('L0', 'L1', 'L2')", name="ck_qa_result_level"),
            sa.CheckConstraint(
                "status IN ('PASS', 'FAIL', 'WARN', 'INFO', 'SKIP')",
                name="ck_qa_result_status",
            ),
            sa.CheckConstraint(
                "severity IN ('critical', 'high', 'medium', 'low', 'info')",
                name="ck_qa_result_severity",
            ),
        )

    _create_index_if_missing(
        "uq_qa_runs_trigger_event_id",
        "qa_acceptance_runs",
        ["trigger_event_id"],
        unique=True,
        postgresql_where=sa.text("trigger_event_id IS NOT NULL"),
    )
    _create_index_if_missing(
        "idx_qa_runs_agent_created_at",
        "qa_acceptance_runs",
        ["agent_name", sa.text("created_at DESC")],
    )
    _create_index_if_missing(
        "idx_qa_runs_commit_sha", "qa_acceptance_runs", ["commit_sha"]
    )
    _create_index_if_missing(
        "idx_qa_runs_mr", "qa_acceptance_runs", ["gitlab_project_id", "mr_iid"]
    )
    _create_index_if_missing(
        "idx_qa_results_run_id", "qa_acceptance_results", ["run_id"]
    )
    _create_index_if_missing(
        "idx_qa_results_level_status",
        "qa_acceptance_results",
        ["level", "status"],
    )
    _create_index_if_missing(
        "idx_qa_results_check_name", "qa_acceptance_results", ["check_name"]
    )


def _create_dev_tables() -> None:
    if not _table_exists("dev_agent_tasks"):
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
                "risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')",
                name="ck_dev_risk_level",
            ),
            sa.CheckConstraint(
                "status IN ('pending','planning','awaiting_approval',"
                "'executing','security_scanning','mr_creating','mr_created',"
                "'qa_triggered','reviewing','completed','failed','expired')",
                name="ck_dev_status",
            ),
            sa.UniqueConstraint("wp_id"),
        )

    if not _table_exists("dev_agent_workflow_logs"):
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

    _create_index_if_missing(
        "idx_dev_tasks_status", "dev_agent_tasks", ["status", "created_at"]
    )
    _create_index_if_missing(
        "idx_dev_tasks_workflow_id", "dev_agent_tasks", ["workflow_id"]
    )
    _create_index_if_missing("idx_dev_tasks_mr_iid", "dev_agent_tasks", ["mr_iid"])


def _create_user_interaction_tables() -> None:
    if not _table_exists("chat_agent_conversation_histories"):
        op.create_table(
            "chat_agent_conversation_histories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("messages", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists("chat_agent_card_operations"):
        op.create_table(
            "chat_agent_card_operations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("user_name", sa.String(length=100), nullable=False),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("table_id", sa.String(length=100), nullable=False),
            sa.Column("record_id", sa.String(length=100), nullable=False),
            sa.Column("assignee_name", sa.String(length=100), nullable=False),
            sa.Column("fields_snapshot", sa.Text(), nullable=True),
            sa.Column("result", sa.String(length=20), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists("chat_agent_daily_progress"):
        op.create_table(
            "chat_agent_daily_progress",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("user_name", sa.String(length=100), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("task_record_id", sa.String(length=100), nullable=False),
            sa.Column("task_title", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("raw_reply", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    _create_index_if_missing(
        "ix_chat_agent_conversation_histories_user_id",
        "chat_agent_conversation_histories",
        ["user_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_chat_agent_card_operations_user_id",
        "chat_agent_card_operations",
        ["user_id"],
    )
    _create_index_if_missing(
        "ix_chat_agent_card_operations_action",
        "chat_agent_card_operations",
        ["action"],
    )
    _create_index_if_missing(
        "ix_chat_agent_card_operations_created_at",
        "chat_agent_card_operations",
        ["created_at"],
    )
    _create_index_if_missing(
        "ix_chat_agent_daily_progress_user_id",
        "chat_agent_daily_progress",
        ["user_id"],
    )
    _create_index_if_missing(
        "ix_chat_agent_daily_progress_date",
        "chat_agent_daily_progress",
        ["date"],
    )


def _create_sync_tables() -> None:
    if not _table_exists("sync_agent_mappings"):
        op.create_table(
            "sync_agent_mappings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("op_work_package_id", sa.Integer(), nullable=False),
            sa.Column("feishu_record_id", sa.String(length=64), nullable=True),
            sa.Column("op_project_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("last_op_update", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_feishu_update", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists("sync_agent_subtask_mappings"):
        op.create_table(
            "sync_agent_subtask_mappings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("parent_op_id", sa.Integer(), nullable=False),
            sa.Column("feishu_record_id", sa.String(length=64), nullable=False),
            sa.Column("subtask_name", sa.String(length=500), nullable=True),
            sa.Column("subtask_status", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists("sync_agent_logs"):
        op.create_table(
            "sync_agent_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sync_type", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("records_processed", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "sync_type IN ('op_to_feishu', 'feishu_to_op', 'full')",
                name="ck_sync_type",
            ),
            sa.CheckConstraint(
                "status IN ('started', 'completed', 'failed')",
                name="ck_sync_status",
            ),
        )

    if not _table_exists("sync_agent_locks"):
        op.create_table(
            "sync_agent_locks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("lock_name", sa.String(length=100), nullable=False),
            sa.Column("locked_by", sa.String(length=100), nullable=True),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_locked", sa.Boolean(), nullable=True),
        )

    _create_index_if_missing(
        "ix_sync_agent_mappings_op_work_package_id",
        "sync_agent_mappings",
        ["op_work_package_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_sync_agent_mappings_feishu_record_id",
        "sync_agent_mappings",
        ["feishu_record_id"],
    )
    _create_index_if_missing(
        "ix_sync_agent_subtask_mappings_parent_op_id",
        "sync_agent_subtask_mappings",
        ["parent_op_id"],
    )
    _create_index_if_missing(
        "ix_sync_agent_subtask_mappings_feishu_record_id",
        "sync_agent_subtask_mappings",
        ["feishu_record_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_sync_agent_locks_lock_name",
        "sync_agent_locks",
        ["lock_name"],
        unique=True,
    )


def _create_analysis_tables() -> None:
    if not _table_exists("analysis_agent_report_logs"):
        op.create_table(
            "analysis_agent_report_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_type", sa.String(length=20), nullable=False),
            sa.Column("report_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "report_type IN ('daily', 'weekly', 'milestone')",
                name="ck_report_type",
            ),
            sa.CheckConstraint(
                "status IN ('generated', 'pushed', 'failed')",
                name="ck_report_status",
            ),
        )


def _create_evolution_tables() -> None:
    if not _table_exists("evolution_traces"):
        op.create_table(
            "evolution_traces",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("agent_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("input_event", sa.JSON(), nullable=True),
            sa.Column("output_events", sa.JSON(), nullable=True),
            sa.Column("llm_calls", sa.JSON(), nullable=True),
            sa.Column("skill_used", sa.String(length=128), nullable=True),
            sa.Column("skill_version", sa.String(length=32), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("human_rating", sa.Integer(), nullable=True),
            sa.Column("human_correction", sa.Text(), nullable=True),
            sa.Column("auto_score", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("evolution_skill_configs"):
        op.create_table(
            "evolution_skill_configs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("skill_id", sa.String(length=128), nullable=False),
            sa.Column("version", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("system_prompt", sa.Text(), nullable=False),
            sa.Column("parameters", sa.JSON(), nullable=True),
            sa.Column("few_shot_examples", sa.JSON(), nullable=True),
            sa.Column("output_format", sa.Text(), nullable=False),
            sa.Column("target_model", sa.String(length=64), nullable=False),
            sa.Column("total_executions", sa.Integer(), nullable=False),
            sa.Column("success_rate", sa.Float(), nullable=False),
            sa.Column("avg_human_rating", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("skill_id", "version", name="uq_skill_id_version"),
        )

    if not _table_exists("evolution_reflections"):
        op.create_table(
            "evolution_reflections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_id", sa.String(length=64), nullable=False),
            sa.Column("skill_id", sa.String(length=128), nullable=False),
            sa.Column("success_patterns", sa.JSON(), nullable=True),
            sa.Column("failure_patterns", sa.JSON(), nullable=True),
            sa.Column("optimization_suggestions", sa.JSON(), nullable=True),
            sa.Column("human_corrections_summary", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("evolution_experiments"):
        op.create_table(
            "evolution_experiments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("experiment_id", sa.String(length=64), nullable=False),
            sa.Column("agent_id", sa.String(length=64), nullable=False),
            sa.Column("skill_id", sa.String(length=128), nullable=False),
            sa.Column("control_version", sa.Integer(), nullable=False),
            sa.Column("candidate_version", sa.Integer(), nullable=False),
            sa.Column("traffic_pct", sa.Integer(), nullable=False),
            sa.Column("min_samples", sa.Integer(), nullable=False),
            sa.Column("max_duration_hours", sa.Integer(), nullable=False),
            sa.Column("success_metric", sa.String(length=64), nullable=False),
            sa.Column("min_improvement", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("control_results", sa.JSON(), nullable=True),
            sa.Column("candidate_results", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("experiment_id"),
        )

    if not _table_exists("evolution_memory"):
        op.create_table(
            "evolution_memory",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_id", sa.String(length=64), nullable=False),
            sa.Column("memory_type", sa.String(length=20), nullable=False),
            sa.Column("key", sa.String(length=256), nullable=False),
            sa.Column("value", sa.JSON(), nullable=True),
            sa.Column("ttl_seconds", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("agent_id", "key", name="uq_agent_id_key"),
        )

    if not _table_exists("evolution_collaboration_patterns"):
        op.create_table(
            "evolution_collaboration_patterns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pattern_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("trigger_event", sa.String(length=128), nullable=False),
            sa.Column("trigger_condition", sa.Text(), nullable=True),
            sa.Column("steps", sa.JSON(), nullable=True),
            sa.Column("shadow_results", sa.JSON(), nullable=True),
            sa.Column("production_results", sa.JSON(), nullable=True),
            sa.Column("human_approval", sa.Boolean(), nullable=False),
            sa.Column("approved_by", sa.String(length=64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("pattern_id"),
        )

    _create_index_if_missing("ix_evolution_traces_trace_id", "evolution_traces", ["trace_id"])
    _create_index_if_missing("ix_evolution_traces_agent_id", "evolution_traces", ["agent_id"])
    _create_index_if_missing(
        "ix_evolution_traces_agent_skill",
        "evolution_traces",
        ["agent_id", "skill_used"],
    )
    _create_index_if_missing(
        "ix_evolution_skill_configs_skill_id",
        "evolution_skill_configs",
        ["skill_id"],
    )
    _create_index_if_missing(
        "ix_evolution_reflections_agent_id",
        "evolution_reflections",
        ["agent_id"],
    )
    _create_index_if_missing(
        "ix_evolution_experiments_agent_id",
        "evolution_experiments",
        ["agent_id"],
    )
    _create_index_if_missing(
        "ix_evolution_memory_agent_id",
        "evolution_memory",
        ["agent_id"],
    )
