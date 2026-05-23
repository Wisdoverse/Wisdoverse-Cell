"""Unit tests for the coordinator replay tool (DDD-018 / ADR-0008)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.orchestration.coordinator.app.replay import (
    _consistency_check,
    _parse_args,
    _render,
)
from services.orchestration.coordinator.db.models import (
    AgentStateRecord,
    DecisionRecord,
    WorkflowState,
)


def _workflow(workflow_id: str, agents: list[str]) -> WorkflowState:
    return WorkflowState(
        workflow_id=workflow_id,
        type="decompose-task",
        status="active",
        current_phase="planning",
        agents_involved=agents,
        created_at=datetime(2026, 5, 23, 10, tzinfo=UTC),
        updated_at=datetime(2026, 5, 23, 11, tzinfo=UTC),
        context={"goal_id": "g_1"},
    )


def _decision(
    *,
    decision_id: str,
    workflow_id: str | None,
    target_agent: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        workflow_id=workflow_id,
        reasoning="r",
        action="dispatch",
        target_agent=target_agent,
        created_at=datetime(2026, 5, 23, 12, tzinfo=UTC),
    )


def _agent_state(agent_id: str) -> AgentStateRecord:
    return AgentStateRecord(
        agent_id=agent_id,
        status="idle",
        current_task=None,
    )


def test_render_handles_missing_workflow() -> None:
    snapshot = {
        "workflow": None,
        "related_decisions": [],
        "related_agent_states": {},
        "all_pending_decisions_count": 5,
        "all_agent_states_count": 3,
    }
    output = _render(snapshot, issues=[])
    assert "workflow: not found" in output
    assert "pending_decisions_total=5" in output
    assert "agent_states_total=3" in output


def test_render_workflow_with_decisions_and_states() -> None:
    workflow = _workflow("wf_1", ["agent_a"])
    snapshot = {
        "workflow": workflow,
        "related_decisions": [
            _decision(decision_id="d_1", workflow_id="wf_1", target_agent="agent_a"),
        ],
        "related_agent_states": {"agent_a": _agent_state("agent_a")},
        "all_pending_decisions_count": 1,
        "all_agent_states_count": 1,
    }
    output = _render(snapshot, issues=[])
    assert "workflow_id=wf_1" in output
    assert "agents_involved=['agent_a']" in output
    assert "decision_id=d_1" in output
    assert "agent_id=agent_a" in output
    assert "consistency: OK" in output


def test_consistency_check_flags_decision_targeting_unknown_agent() -> None:
    workflow = _workflow("wf_1", ["agent_a"])
    snapshot = {
        "workflow": workflow,
        "related_decisions": [
            _decision(decision_id="d_1", workflow_id="wf_1", target_agent="agent_b"),
        ],
        "related_agent_states": {"agent_a": _agent_state("agent_a")},
        "all_pending_decisions_count": 1,
        "all_agent_states_count": 1,
    }
    issues = _consistency_check(snapshot)
    assert any("agents_involved" in issue for issue in issues)
    assert any("no agent_state row" in issue for issue in issues)


def test_consistency_check_no_issues_for_aligned_state() -> None:
    workflow = _workflow("wf_1", ["agent_a", "agent_b"])
    snapshot = {
        "workflow": workflow,
        "related_decisions": [
            _decision(decision_id="d_1", workflow_id="wf_1", target_agent="agent_a"),
            _decision(decision_id="d_2", workflow_id="wf_1", target_agent="agent_b"),
        ],
        "related_agent_states": {
            "agent_a": _agent_state("agent_a"),
            "agent_b": _agent_state("agent_b"),
        },
        "all_pending_decisions_count": 2,
        "all_agent_states_count": 2,
    }
    assert _consistency_check(snapshot) == []


def test_parse_args_accepts_workflow_id_and_json_flag() -> None:
    args = _parse_args(["wf_42"])
    assert args.workflow_id == "wf_42"
    assert args.json is False

    args = _parse_args(["wf_42", "--json"])
    assert args.json is True


def test_parse_args_requires_workflow_id() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])
