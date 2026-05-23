"""Smoke tests for the coordinator durable-state SQLAlchemy tables (DDD-018)."""

from __future__ import annotations

from services.orchestration.coordinator.db.state_tables import (
    CoordinatorAgentState,
    CoordinatorPendingDecision,
    CoordinatorWorkflowState,
)


def test_agent_state_table_metadata() -> None:
    assert CoordinatorAgentState.__tablename__ == "coordinator_agent_state"
    cols = {c.name for c in CoordinatorAgentState.__table__.columns}
    assert {"agent_id", "status", "current_task", "last_output_at", "error", "updated_at"} <= cols


def test_workflow_state_table_metadata() -> None:
    assert CoordinatorWorkflowState.__tablename__ == "coordinator_workflow_state"
    cols = {c.name for c in CoordinatorWorkflowState.__table__.columns}
    assert {
        "workflow_id",
        "type",
        "status",
        "current_phase",
        "agents_involved",
        "context",
        "created_at",
        "updated_at",
    } <= cols


def test_pending_decision_table_metadata() -> None:
    assert CoordinatorPendingDecision.__tablename__ == "coordinator_pending_decision"
    cols = {c.name for c in CoordinatorPendingDecision.__table__.columns}
    assert {
        "decision_id",
        "workflow_id",
        "reasoning",
        "action",
        "target_agent",
        "task_id",
        "outcome",
        "created_at",
        "resolved_at",
        "retry_count",
    } <= cols


def test_postgres_state_store_imports_clean() -> None:
    """Adapter module imports without error."""
    from services.orchestration.coordinator.db.postgres_state_store import (
        PostgresCoordinatorStateStore,
    )

    assert PostgresCoordinatorStateStore.PENDING_DECISIONS_LIMIT == 100
