"""Tests for Coordinator workflow-state aggregate."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.orchestration.coordinator.core.domain.workflow_state import (
    CoordinatorWorkflowState,
    CoordinatorWorkflowStatus,
    InvalidCoordinatorWorkflowError,
    InvalidCoordinatorWorkflowTransitionError,
)
from services.orchestration.coordinator.db.models import WorkflowState


def test_workflow_state_aggregate_validates_and_serializes_record_fields() -> None:
    """Workflow state owns non-empty fields and agent-list uniqueness."""
    aggregate = CoordinatorWorkflowState.create(
        workflow_id=" wf_1 ",
        workflow_type="delivery",
        current_phase="planning",
        agents_involved=["dev-agent", "qa-agent"],
        context={"goal_id": "goal_1"},
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
    )

    aggregate.add_agent("qa-agent")
    aggregate.add_agent("chat-agent")
    aggregate.advance_phase("execution")

    record = aggregate.to_record_kwargs()
    assert record["workflow_id"] == "wf_1"
    assert record["type"] == "delivery"
    assert record["status"] == "active"
    assert record["current_phase"] == "execution"
    assert record["agents_involved"] == ["dev-agent", "qa-agent", "chat-agent"]
    assert record["context"] == {"goal_id": "goal_1"}

    with pytest.raises(InvalidCoordinatorWorkflowError):
        CoordinatorWorkflowState.create(
            workflow_id="wf_2",
            workflow_type="delivery",
            current_phase="planning",
            agents_involved=["dev-agent", "dev-agent"],
        )


def test_workflow_state_aggregate_guards_status_transitions() -> None:
    """Coordinator workflow status changes follow an explicit FSM."""
    aggregate = CoordinatorWorkflowState.create(
        workflow_id="wf_status",
        workflow_type="delivery",
        current_phase="planning",
        agents_involved=["dev-agent"],
    )

    aggregate.transition_to(CoordinatorWorkflowStatus.PAUSED)
    aggregate.transition_to(CoordinatorWorkflowStatus.ACTIVE)
    aggregate.transition_to(CoordinatorWorkflowStatus.COMPLETED)

    events = aggregate.pull_events()
    assert [event.status for event in events] == [
        CoordinatorWorkflowStatus.PAUSED,
        CoordinatorWorkflowStatus.ACTIVE,
        CoordinatorWorkflowStatus.COMPLETED,
    ]
    assert events[0].to_payload()["previous_status"] == "active"
    assert aggregate.status == CoordinatorWorkflowStatus.COMPLETED

    with pytest.raises(InvalidCoordinatorWorkflowTransitionError):
        aggregate.transition_to(CoordinatorWorkflowStatus.ACTIVE)


def test_workflow_state_aggregate_hydrates_from_persistence_record() -> None:
    """Persisted Pydantic state rows are validated through the aggregate."""
    record = WorkflowState(
        workflow_id="wf_row",
        type="delivery",
        status="paused",
        current_phase="planning",
        agents_involved=["pjm-agent"],
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
        updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        context={},
    )

    aggregate = CoordinatorWorkflowState.from_record(record)

    assert aggregate.workflow_id == "wf_row"
    assert aggregate.status == CoordinatorWorkflowStatus.PAUSED
    assert aggregate.agents_involved == ("pjm-agent",)
