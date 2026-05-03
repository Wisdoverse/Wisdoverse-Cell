"""Unit tests for WorkflowPlanner JSON extraction."""
import pytest

from agents.dev_agent.core.config import DevCoreConfig
from agents.dev_agent.core.prompts import WORKFLOW_PLANNER_SYSTEM
from agents.dev_agent.core.workflow_planner import WorkflowPlanner, extract_json
from agents.dev_agent.models.schemas import SanitizedTask


def test_extract_json_plain():
    assert extract_json('{"name": "test", "nodes": []}') == {"name": "test", "nodes": []}


def test_extract_json_markdown_fences():
    raw = '```json\n{"name": "test", "nodes": []}\n```'
    assert extract_json(raw) == {"name": "test", "nodes": []}


def test_extract_json_surrounding_text():
    raw = 'Here is the plan:\n{"name": "test", "nodes": []}\nDone!'
    assert extract_json(raw) == {"name": "test", "nodes": []}


def test_extract_json_invalid():
    assert extract_json("not json at all") is None


def test_extract_json_empty():
    assert extract_json("") is None
    assert extract_json(None) is None


def test_extract_json_nested():
    raw = '{"name": "x", "nodes": [{"name": "a", "config": {"k": "v"}}]}'
    result = extract_json(raw)
    assert result["nodes"][0]["config"]["k"] == "v"


def test_workflow_planner_prompt_requires_git_push_acceptance_step():
    assert (
        "git checkout -B dev/wp-{wp_id} && git add -A && git commit -m "
        '"dev(wp-{wp_id}): auto" && git push --force-with-lease origin dev/wp-{wp_id}'
    ) in WORKFLOW_PLANNER_SYSTEM


class FakeLLMGateway:
    def __init__(self) -> None:
        self.calls = []

    async def complete(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return '{"name": "wf", "nodes": [{"name": "plan", "config": {}}]}'


@pytest.mark.asyncio
async def test_workflow_planner_uses_injected_model():
    llm = FakeLLMGateway()
    planner = WorkflowPlanner(
        llm,
        config=DevCoreConfig.from_values(decompose_model="planner-model"),
    )

    plan = await planner.plan(
        SanitizedTask(
            title="Implement feature",
            description="Create a small change",
            estimated_hours=2,
            wp_id=123,
        )
    )

    assert plan is not None
    assert llm.calls[0]["model"] == "planner-model"
