"""Tests for AgentMemory three-scope persistence."""
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def memory(tmp_path):
    from shared.infra.agent_memory import AgentMemory
    mem = AgentMemory(agent_id="dev-agent", base_dir=str(tmp_path / "agent-memory"))
    return mem


@pytest_asyncio.fixture
async def coord_memory(tmp_path):
    from shared.infra.agent_memory import AgentMemory
    mem = AgentMemory(agent_id="coordinator", base_dir=str(tmp_path / "agent-memory"), is_coordinator=True)
    return mem


@pytest.mark.asyncio
async def test_load_context_empty(memory):
    ctx = await memory.load_context()
    assert ctx == ""


@pytest.mark.asyncio
async def test_save_and_load_agent_scope(memory):
    await memory.save(memory._agent_id, "patterns.md", "# Coding Patterns\nUse async everywhere")
    ctx = await memory.load_context()
    assert "Coding Patterns" in ctx


@pytest.mark.asyncio
async def test_save_to_workflow_scope(memory):
    await memory.save("workflows/wf_001", "prd.md", "# PRD\nFeature X", workflow_id="wf_001")
    ctx = await memory.load_context(workflow_id="wf_001")
    assert "PRD" in ctx
    assert "Feature X" in ctx


@pytest.mark.asyncio
async def test_save_rejects_other_agent_scope(memory):
    with pytest.raises(PermissionError):
        await memory.save("qa-agent", "notes.md", "should fail")


@pytest.mark.asyncio
async def test_save_rejects_global_for_regular_agent(memory):
    with pytest.raises(PermissionError):
        await memory.save("global", "decisions.md", "should fail")


@pytest.mark.asyncio
async def test_save_rejects_workflow_without_workflow_id(memory):
    with pytest.raises(PermissionError):
        await memory.save("workflows/wf_001", "prd.md", "should fail")


@pytest.mark.asyncio
async def test_coordinator_can_write_global(coord_memory):
    await coord_memory.save("global", "architecture.md", "# Architecture\nEvent-driven")
    ctx = await coord_memory.load_context()
    assert "Architecture" in ctx


@pytest.mark.asyncio
async def test_coordinator_can_write_any_agent_scope(coord_memory):
    await coord_memory.save("dev-agent", "feedback.md", "# Feedback\nImprove error handling")
    # Coordinator reads all scopes
    content = await coord_memory._read_scope("dev-agent")
    assert "Feedback" in content


@pytest.mark.asyncio
async def test_load_context_combines_all_scopes(memory, coord_memory):
    # Write to global (via coordinator)
    await coord_memory.save("global", "rules.md", "# Rules\nAsync only")
    # Write to agent scope
    await memory.save("dev-agent", "notes.md", "# Notes\nUse TDD")

    ctx = await memory.load_context()
    assert "Rules" in ctx
    assert "Notes" in ctx


@pytest.mark.asyncio
async def test_load_context_with_workflow(memory, coord_memory):
    await coord_memory.save("global", "rules.md", "# Global Rules")
    await memory.save("dev-agent", "notes.md", "# Agent Notes")
    await memory.save("workflows/wf_001", "prd.md", "# Workflow PRD", workflow_id="wf_001")

    ctx = await memory.load_context(workflow_id="wf_001")
    assert "Global Rules" in ctx
    assert "Agent Notes" in ctx
    assert "Workflow PRD" in ctx
