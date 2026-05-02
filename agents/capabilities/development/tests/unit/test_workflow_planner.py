"""Unit tests for WorkflowPlanner JSON extraction."""
from agents.capabilities.development.core.prompts import WORKFLOW_PLANNER_SYSTEM
from agents.capabilities.development.core.workflow_planner import extract_json


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
