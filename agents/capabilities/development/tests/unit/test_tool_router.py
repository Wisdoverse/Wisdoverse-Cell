import pytest

from agents.capabilities.development.core.tool_router import ToolRouter
from agents.capabilities.development.models.schemas import WorkflowNode


@pytest.fixture
def router():
    return ToolRouter()


def test_plan_routes_to_codex(router):
    node = WorkflowNode(name="plan", config={"tags": ["plan"]})
    assert router.route(node) == "codex"


def test_implement_routes_to_claude(router):
    node = WorkflowNode(name="impl", config={"tags": ["implement"]})
    assert router.route(node) == "claude"


def test_tests_routes_to_gemini(router):
    node = WorkflowNode(name="tests", config={"tags": ["tests"]})
    assert router.route(node) == "gemini"


def test_no_match_defaults_to_claude(router):
    node = WorkflowNode(name="unknown", config={"tags": ["mystery"]})
    assert router.route(node) == "claude"


def test_higher_priority_wins(router):
    node = WorkflowNode(name="x", config={"tags": ["plan", "implement"]})
    assert router.route(node) == "codex"


def test_config_override(router):
    router.set_overrides({"impl-*": "gemini"})
    node = WorkflowNode(name="impl-core", config={"tags": ["implement"]})
    assert router.route(node) == "gemini"


def test_no_tags_defaults(router):
    node = WorkflowNode(name="x", config={})
    assert router.route(node) == "claude"
