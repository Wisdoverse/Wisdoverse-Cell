"""Coordinator state-record domain tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services.orchestration.coordinator.core.domain.state_records import (
    CoordinatorAgentId,
    CoordinatorAgentStateRecord,
    CoordinatorAgentStatus,
    CoordinatorDecisionId,
    CoordinatorDecisionRecord,
    CoordinatorTaskId,
    CoordinatorWorkflowId,
)


def test_agent_state_record_normalizes_identity_and_status() -> None:
    record = CoordinatorAgentStateRecord.create(
        agent_id="dev-agent",
        status="working",
        current_task="task_1",
        last_output_at=datetime(2026, 5, 23, tzinfo=UTC),
    )

    assert record.agent_id == CoordinatorAgentId("dev-agent")
    assert record.status is CoordinatorAgentStatus.WORKING
    assert record.current_task == CoordinatorTaskId("task_1")
    assert record.model_dump() == {
        "agent_id": "dev-agent",
        "status": "working",
        "current_task": "task_1",
        "last_output_at": datetime(2026, 5, 23, tzinfo=UTC),
        "error": None,
    }


def test_decision_record_normalizes_persisted_decision_identity() -> None:
    row = SimpleNamespace(
        decision_id="dec_1",
        workflow_id="wf_1",
        reasoning="PRD approved",
        action="dispatch_task",
        target_agent="dev-agent",
        task_id="task_1",
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
        outcome=None,
    )

    record = CoordinatorDecisionRecord.from_record(row)

    assert record.decision_id == CoordinatorDecisionId("dec_1")
    assert record.workflow_id == CoordinatorWorkflowId("wf_1")
    assert record.target_agent == CoordinatorAgentId("dev-agent")
    assert record.task_id == CoordinatorTaskId("task_1")
    assert record.model_dump()["target_agent"] == "dev-agent"


def test_state_records_reject_empty_identity_and_action() -> None:
    with pytest.raises(ValueError):
        CoordinatorAgentStateRecord.create(agent_id=" ", status="idle")

    with pytest.raises(ValueError):
        CoordinatorDecisionRecord.create(
            decision_id="dec_1",
            reasoning="",
            action=" ",
            target_agent="dev-agent",
        )
