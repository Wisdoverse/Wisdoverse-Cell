"""Tests for Tool Registry — unified tool interface."""

import pytest


def test_tool_meta_fail_closed_defaults():
    from shared.infra.tool_registry import ToolMeta
    meta = ToolMeta(name="test_tool", description="A test tool")
    assert meta.is_read_only is False
    assert meta.is_concurrency_safe is False
    assert meta.is_destructive is False
    assert meta.should_defer is False
    assert meta.requires_approval is False


def test_tool_meta_explicit_values():
    from shared.infra.tool_registry import ToolMeta
    meta = ToolMeta(
        name="read_file",
        description="Read a file",
        is_read_only=True,
        is_concurrency_safe=True,
    )
    assert meta.is_read_only is True
    assert meta.is_concurrency_safe is True


def test_build_tool_creates_tool():
    from shared.infra.tool_registry import ToolContext, ToolResult, build_tool

    async def handler(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data={"echo": input.get("msg")})

    tool = build_tool(
        name="echo",
        description="Echo input",
        handler=handler,
        is_read_only=True,
    )
    assert tool.meta.name == "echo"
    assert tool.meta.is_read_only is True
    assert tool.meta.is_concurrency_safe is False  # fail-closed default


@pytest.mark.asyncio
async def test_built_tool_execute():
    from shared.infra.tool_registry import ToolContext, ToolResult, build_tool

    async def handler(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data={"value": input["x"] * 2})

    tool = build_tool(name="double", description="Double input", handler=handler)
    ctx = ToolContext(agent_id="test-agent", task_id="t1")
    result = await tool.execute({"x": 5}, ctx)
    assert result.success is True
    assert result.data["value"] == 10


def test_registry_register_and_get():
    from shared.infra.tool_registry import (
        ToolContext,
        ToolRegistry,
        ToolResult,
        build_tool,
    )

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    registry = ToolRegistry()
    tool = build_tool(name="noop", description="No-op", handler=noop)
    registry.register(tool)

    assert registry.get("noop") is tool
    assert registry.get("nonexistent") is None


def test_registry_list_for_agent_no_permissions():
    from shared.infra.tool_registry import ToolContext, ToolRegistry, ToolResult, build_tool

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(build_tool(name="a", description="A", handler=noop))
    registry.register(build_tool(name="b", description="B", handler=noop))

    tools = registry.list_for_agent("dev-agent")
    assert len(tools) == 2


def test_registry_list_for_agent_with_allowed():
    from shared.infra.tool_registry import ToolContext, ToolRegistry, ToolResult, build_tool
    from shared.schemas.coordinator import DispatchPermissions

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(build_tool(name="git_commit", description="Git commit", handler=noop))
    registry.register(build_tool(name="file_read", description="Read file", handler=noop))
    registry.register(build_tool(name="file_delete", description="Delete file", handler=noop))

    perms = DispatchPermissions(allowed_tools=["git_commit", "file_read"])
    tools = registry.list_for_agent("dev-agent", permissions=perms)
    names = [t.meta.name for t in tools]
    assert "git_commit" in names
    assert "file_read" in names
    assert "file_delete" not in names


def test_registry_list_for_agent_with_denied():
    from shared.infra.tool_registry import ToolContext, ToolRegistry, ToolResult, build_tool
    from shared.schemas.coordinator import DispatchPermissions

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(build_tool(name="a", description="A", handler=noop))
    registry.register(build_tool(name="b", description="B", handler=noop))
    registry.register(build_tool(name="c", description="C", handler=noop))

    perms = DispatchPermissions(denied_tools=["b"])
    tools = registry.list_for_agent("dev-agent", permissions=perms)
    names = [t.meta.name for t in tools]
    assert "a" in names
    assert "c" in names
    assert "b" not in names


def test_registry_get_read_only():
    from shared.infra.tool_registry import ToolContext, ToolRegistry, ToolResult, build_tool

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(build_tool(name="reader", description="Read", handler=noop, is_read_only=True))
    registry.register(build_tool(name="writer", description="Write", handler=noop))

    ro = registry.get_read_only()
    assert len(ro) == 1
    assert ro[0].meta.name == "reader"


def test_registry_get_deferred():
    from shared.infra.tool_registry import ToolContext, ToolRegistry, ToolResult, build_tool

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(build_tool(name="fast", description="Fast", handler=noop))
    registry.register(build_tool(name="slow", description="Slow", handler=noop, should_defer=True))

    deferred = registry.get_deferred()
    assert deferred == ["slow"]


# ── Raw schema preservation (P0 fix) ────────────────────────────────────────


def _noop_handler():
    from shared.infra.tool_registry import ToolContext, ToolResult

    async def noop(input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True)
    return noop


_RICH_SCHEMA = {
    "name": "update_task",
    "description": "Update a task",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task ID"},
            "status": {"type": "string", "enum": ["open", "closed"]},
        },
        "required": ["task_id", "status"],
    },
}


def test_register_raw_schema_preserved_in_to_anthropic_schemas():
    """Non-deferred tools should return their real input_schema, not empty stub."""
    from shared.infra.tool_registry import ToolRegistry, build_tool

    registry = ToolRegistry()
    tool = build_tool(name="update_task", description="Update a task", handler=_noop_handler())
    registry.register(tool)
    registry.register_raw_schema("update_task", _RICH_SCHEMA)

    schemas = registry.to_anthropic_schemas()
    # Find update_task in schemas (tool_search is also appended)
    update_schema = next(s for s in schemas if s["name"] == "update_task")

    assert update_schema["input_schema"]["properties"]["task_id"]["type"] == "string"
    assert update_schema["input_schema"]["required"] == ["task_id", "status"]


def test_deferred_tool_returns_stub_even_with_raw_schema():
    """Deferred tools not in active_deferred should return stub (name+desc only)."""
    from shared.infra.tool_registry import ToolRegistry, build_tool

    registry = ToolRegistry()
    tool = build_tool(
        name="slow_tool", description="A slow tool",
        handler=_noop_handler(), should_defer=True,
    )
    registry.register(tool)
    registry.register_raw_schema("slow_tool", {
        "name": "slow_tool", "description": "A slow tool",
        "input_schema": {"type": "object", "properties": {"x": {"type": "int"}}, "required": ["x"]},
    })

    schemas = registry.to_anthropic_schemas(active_deferred=None)
    slow_schema = next(s for s in schemas if s["name"] == "slow_tool")

    # Stub: empty properties
    assert slow_schema["input_schema"]["properties"] == {}


def test_deferred_tool_returns_full_schema_when_active():
    """Deferred tools in active_deferred should return their full raw schema."""
    from shared.infra.tool_registry import ToolRegistry, build_tool

    registry = ToolRegistry()
    tool = build_tool(
        name="slow_tool", description="A slow tool",
        handler=_noop_handler(), should_defer=True,
    )
    registry.register(tool)
    registry.register_raw_schema("slow_tool", {
        "name": "slow_tool", "description": "A slow tool",
        "input_schema": {"type": "object", "properties": {"x": {"type": "int"}}, "required": ["x"]},
    })

    schemas = registry.to_anthropic_schemas(active_deferred={"slow_tool"})
    slow_schema = next(s for s in schemas if s["name"] == "slow_tool")

    assert slow_schema["input_schema"]["properties"]["x"]["type"] == "int"


def test_to_anthropic_schemas_without_raw_schema_falls_back_to_stub():
    """Tools without register_raw_schema still get a stub (backward compat)."""
    from shared.infra.tool_registry import ToolRegistry, build_tool

    registry = ToolRegistry()
    tool = build_tool(name="simple", description="Simple tool", handler=_noop_handler())
    registry.register(tool)

    schemas = registry.to_anthropic_schemas()
    simple_schema = next(s for s in schemas if s["name"] == "simple")

    assert simple_schema["input_schema"]["properties"] == {}


def test_search_tools_returns_raw_schema_for_matches():
    """search_tools should return the rich schema for matching deferred tools."""
    from shared.infra.tool_registry import ToolRegistry, build_tool

    registry = ToolRegistry()
    tool = build_tool(
        name="sync_now", description="Trigger sync",
        handler=_noop_handler(), should_defer=True,
    )
    registry.register(tool)
    registry.register_raw_schema("sync_now", {
        "name": "sync_now", "description": "Trigger sync",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    })

    results = registry.search_tools("sync")
    assert len(results) == 1
    assert results[0]["name"] == "sync_now"
