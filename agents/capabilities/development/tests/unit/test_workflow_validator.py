import pytest

from agents.capabilities.development.core.workflow_validator import WorkflowValidator
from agents.capabilities.development.models.schemas import WorkflowNode, WorkflowPlan


@pytest.fixture
def validator():
    return WorkflowValidator()


def _make_plan(nodes):
    return WorkflowPlan(name="test", description="test", nodes=nodes)


def test_valid_plan_passes(validator):
    plan = _make_plan([
        WorkflowNode(
            name="plan",
            config={
                "prompt": "Edit agents/capabilities/development/core/prompts.py",
                "tags": ["plan"],
            },
        ),
        WorkflowNode(
            name="impl",
            dependsOn=["plan"],
            config={
                "prompt": "Update agents/capabilities/development/core/workflow_validator.py",
                "tags": ["implement"],
            },
        ),
        WorkflowNode(
            name="review",
            dependsOn=["impl"],
            config={
                "prompt": "Review agents/capabilities/development/tests/unit/test_workflow_validator.py",
                "tags": ["review"],
            },
        ),
        WorkflowNode(
            name="acceptance",
            dependsOn=["review"],
            config={
                "prompt": (
                    "Verify agents/capabilities/development/tests/unit/test_workflow_validator.py "
                    "and git checkout -B dev/wp-123 && git add -A "
                    '&& git commit -m "dev(wp-123): auto" '
                    "&& git push --force-with-lease origin dev/wp-123"
                ),
                "tags": ["acceptance"],
            },
        ),
    ])
    result = validator.validate(plan)
    assert result.is_valid


def test_cyclic_dependency_rejected(validator):
    plan = _make_plan([
        WorkflowNode(name="a", dependsOn=["b"], config={}),
        WorkflowNode(name="b", dependsOn=["a"], config={}),
    ])
    result = validator.validate(plan)
    assert not result.is_valid
    assert any(
        "cycle" in v.lower() or "cyclic" in v.lower() for v in result.violations
    )


def test_missing_review_rejected(validator):
    plan = _make_plan([
        WorkflowNode(name="plan", config={"tags": ["plan"]}),
        WorkflowNode(
            name="impl", dependsOn=["plan"], config={"tags": ["implement"]}
        ),
    ])
    result = validator.validate(plan)
    assert not result.is_valid


def test_path_traversal_rejected(validator):
    plan = _make_plan([
        WorkflowNode(
            name="plan",
            config={"prompt": "Edit ../../.env", "tags": ["plan"]},
        ),
        WorkflowNode(
            name="review", dependsOn=["plan"], config={"tags": ["review"]}
        ),
        WorkflowNode(
            name="acceptance",
            dependsOn=["review"],
            config={"tags": ["acceptance"]},
        ),
    ])
    result = validator.validate(plan)
    assert not result.is_valid


def test_nonexistent_dependency(validator):
    plan = _make_plan([
        WorkflowNode(
            name="a",
            dependsOn=["nonexistent"],
            config={"tags": ["review", "acceptance"]},
        ),
    ])
    result = validator.validate(plan)
    assert not result.is_valid


def test_last_node_without_git_push_rejected(validator):
    plan = _make_plan([
        WorkflowNode(
            name="plan",
            config={
                "prompt": "Edit agents/capabilities/development/core/prompts.py",
                "tags": ["plan"],
            },
        ),
        WorkflowNode(
            name="review",
            dependsOn=["plan"],
            config={
                "prompt": "Review agents/capabilities/development/core/workflow_validator.py",
                "tags": ["review"],
            },
        ),
        WorkflowNode(
            name="acceptance",
            dependsOn=["review"],
            config={
                "prompt": "Run pytest agents/capabilities/development/tests/unit/test_workflow_validator.py -q",
                "tags": ["acceptance"],
            },
        ),
    ])
    result = validator.validate(plan)
    assert not result.is_valid
    assert any("git push" in violation.lower() for violation in result.violations)


def test_push_to_wrong_branch_rejected(validator):
    """Validator rejects push to a branch that isn't dev/wp-<id>."""
    plan = _make_plan([
        WorkflowNode(
            name="plan",
            config={
                "prompt": "Edit agents/capabilities/development/core/prompts.py",
                "tags": ["plan"],
            },
        ),
        WorkflowNode(
            name="review",
            dependsOn=["plan"],
            config={
                "prompt": "Review agents/capabilities/development/core/workflow_validator.py",
                "tags": ["review"],
            },
        ),
        WorkflowNode(
            name="acceptance",
            dependsOn=["review"],
            config={
                "prompt": "git push origin main",
                "tags": ["acceptance"],
            },
        ),
    ])
    result = validator.validate(plan)
    assert not result.is_valid
    assert any("dev/wp-" in v for v in result.violations)
