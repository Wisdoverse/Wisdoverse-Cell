import pytest

from agents.dev_agent.models.schemas import (
    VALID_TRANSITIONS,
    RiskLevel,
    SanitizedTask,
    TaskInput,
    ToolRule,
    WorkflowNode,
    WorkflowPlan,
)


def test_workflow_node_valid():
    node = WorkflowNode(
        name="plan", type="agent_task", dependsOn=[],
        config={"cliTool": "codex", "prompt": "Plan the work", "tags": ["plan"]},
    )
    assert node.name == "plan"


def test_workflow_plan_requires_nodes():
    with pytest.raises(Exception):
        WorkflowPlan(name="test", description="test", nodes=[])


def test_workflow_plan_valid():
    plan = WorkflowPlan(
        name="test", description="test",
        nodes=[WorkflowNode(name="plan", config={"tags": ["plan"]})],
    )
    assert len(plan.nodes) == 1


def test_tool_rule_priority_sorting():
    r1 = ToolRule(match_tags=["plan"], tool="codex", priority=10)
    r2 = ToolRule(match_tags=["impl"], tool="claude", priority=5)
    assert r1.priority > r2.priority


def test_risk_level_enum():
    assert RiskLevel.LOW.value == "LOW"
    assert RiskLevel.CRITICAL.value == "CRITICAL"


def test_valid_transitions_pending():
    assert "planning" in VALID_TRANSITIONS["pending"]
    assert "expired" in VALID_TRANSITIONS["pending"]
    assert "completed" not in VALID_TRANSITIONS["pending"]


def test_valid_transitions_failed_can_retry():
    assert "planning" in VALID_TRANSITIONS["failed"]


def test_valid_transitions_completed_is_terminal():
    assert VALID_TRANSITIONS["completed"] == set()


def test_task_input_title_max_length():
    with pytest.raises(Exception):
        TaskInput(title="x" * 201, description="ok", estimated_hours=4)


def test_task_input_valid():
    task = TaskInput(title="Fix bug", description="Fix the login bug", estimated_hours=4, wp_id=123)
    assert task.wp_id == 123


def test_sanitized_task_has_risk_level():
    task = SanitizedTask(
        title="Fix", description="desc",
        estimated_hours=2, risk_level=RiskLevel.HIGH,
    )
    assert task.risk_level == RiskLevel.HIGH
