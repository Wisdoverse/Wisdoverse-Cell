"""Tests for Scratchpad file-based state management."""
from types import SimpleNamespace

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def scratchpad(tmp_path):
    from shared.infra.scratchpad import Scratchpad
    sp = Scratchpad(base_dir=str(tmp_path / "scratchpad"))
    await sp.initialize()
    return sp


@pytest.mark.asyncio
async def test_initialize_creates_directory_structure(scratchpad, tmp_path):
    base = tmp_path / "scratchpad"
    assert (base / "global_status.md").exists()
    assert (base / "workflows").is_dir()
    assert (base / "agents").is_dir()
    assert (base / "decisions").is_dir()
    assert (base / "decisions" / "pending.md").exists()
    assert (base / "decisions" / "log.md").exists()


@pytest.mark.asyncio
async def test_write_agent_output(scratchpad):
    await scratchpad.write_agent_output("dev-agent", "## Task Complete\nCommit abc123")
    content = await scratchpad.read_agent_output("dev-agent")
    assert "Commit abc123" in content


@pytest.mark.asyncio
async def test_read_nonexistent_agent_output_returns_empty(scratchpad):
    content = await scratchpad.read_agent_output("nonexistent-agent")
    assert content == ""


@pytest.mark.asyncio
async def test_write_workflow(scratchpad):
    await scratchpad.write_workflow("wf_001", "## PRD Phase\nIn progress")
    content = await scratchpad.read_workflow("wf_001")
    assert "PRD Phase" in content


@pytest.mark.asyncio
async def test_update_global_status(scratchpad):
    await scratchpad.update_global_status("All systems nominal")
    content = await scratchpad.read_global_status()
    assert "All systems nominal" in content


@pytest.mark.asyncio
async def test_read_incremental_returns_all_sections(scratchpad):
    await scratchpad.update_global_status("Status OK")
    await scratchpad.write_agent_output("dev-agent", "Dev done")
    await scratchpad.write_workflow("wf_001", "WF active")

    snapshot = await scratchpad.read_incremental()
    assert "Status OK" in snapshot
    assert "Dev done" in snapshot
    assert "WF active" in snapshot


@pytest.mark.asyncio
async def test_append_decision_log(scratchpad):
    await scratchpad.append_decision("Dispatched dev-agent for task_001")
    await scratchpad.append_decision("QA requested for task_001")
    content = await scratchpad.read_decision_log()
    assert "Dispatched dev-agent" in content
    assert "QA requested" in content


@pytest.mark.asyncio
async def test_update_records_decisions_in_log_and_workflow(scratchpad):
    await scratchpad.write_workflow("wf_001", "Existing context")
    decision = SimpleNamespace(
        action="dispatch_task",
        target_agent="dev-agent",
        task_id="task_001",
        workflow_id="wf_001",
        reasoning="PRD approved",
        instruction="Implement the approved requirement",
    )

    await scratchpad.update([decision])

    decision_log = await scratchpad.read_decision_log()
    assert "action: dispatch_task" in decision_log
    assert "target_agent: dev-agent" in decision_log
    assert "workflow_id: wf_001" in decision_log
    assert "reasoning: PRD approved" in decision_log

    workflow = await scratchpad.read_workflow("wf_001")
    assert "Existing context" in workflow
    assert "instruction: Implement the approved requirement" in workflow


@pytest.mark.asyncio
async def test_token_estimate(scratchpad):
    await scratchpad.update_global_status("x" * 1000)
    estimate = await scratchpad.estimate_tokens()
    assert estimate > 200
