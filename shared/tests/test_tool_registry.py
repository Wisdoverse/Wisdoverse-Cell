"""Tests for ToolRegistry deferred-tool loading extensions.

Covers:
- to_anthropic_schemas(): non-deferred full, deferred stub, active_deferred full, tool_search appended
- search_tools(): name match, description match, full schema, no match, deferred-only
- Existing methods unchanged: register/get, get_deferred, get_read_only
"""

from shared.infra.tool_registry import ToolContext, ToolRegistry, ToolResult, build_tool


async def _noop_handler(input: dict, context: ToolContext) -> ToolResult:
    return ToolResult(success=True)


def _make_registry() -> ToolRegistry:
    """3 normal + 2 deferred tools."""
    registry = ToolRegistry()
    # Normal tools
    registry.register(
        build_tool(name="read_file", description="Read a file from disk", handler=_noop_handler, is_read_only=True)
    )
    registry.register(
        build_tool(name="write_file", description="Write content to a file", handler=_noop_handler)
    )
    registry.register(
        build_tool(name="search_code", description="Search code in repo", handler=_noop_handler, is_read_only=True)
    )
    # Deferred tools
    registry.register(
        build_tool(
            name="sync_now",
            description="Sync data to remote server",
            handler=_noop_handler,
            should_defer=True,
        )
    )
    registry.register(
        build_tool(
            name="add_field",
            description="Add a field to the database schema",
            handler=_noop_handler,
            should_defer=True,
        )
    )
    return registry


class TestToAnthropicSchemas:
    """to_anthropic_schemas() tests."""

    def test_non_deferred_have_full_schema(self):
        registry = _make_registry()
        schemas = registry.to_anthropic_schemas()
        by_name = {s["name"]: s for s in schemas}
        schema = by_name["read_file"]
        assert schema["input_schema"]["type"] == "object"
        assert "description" in schema

    def test_deferred_have_stub_schema(self):
        registry = _make_registry()
        schemas = registry.to_anthropic_schemas()
        by_name = {s["name"]: s for s in schemas}
        schema = by_name["sync_now"]
        assert schema["input_schema"] == {"type": "object", "properties": {}}

    def test_active_deferred_get_full_schema(self):
        registry = _make_registry()
        schemas = registry.to_anthropic_schemas(active_deferred={"sync_now"})
        by_name = {s["name"]: s for s in schemas}
        schema = by_name["sync_now"]
        # Active deferred gets full schema (same as non-deferred)
        assert schema["input_schema"]["type"] == "object"
        assert schema["description"] == "Sync data to remote server"
        # The other deferred tool remains a stub
        stub = by_name["add_field"]
        assert stub["input_schema"] == {"type": "object", "properties": {}}

    def test_tool_search_always_included(self):
        registry = _make_registry()
        schemas = registry.to_anthropic_schemas()
        names = [s["name"] for s in schemas]
        assert "tool_search" in names

    def test_schema_count(self):
        """3 normal + 2 deferred + 1 tool_search = 6."""
        registry = _make_registry()
        schemas = registry.to_anthropic_schemas()
        assert len(schemas) == 6


class TestSearchTools:
    """search_tools() tests."""

    def test_search_by_name(self):
        registry = _make_registry()
        results = registry.search_tools("sync")
        names = [r["name"] for r in results]
        assert "sync_now" in names

    def test_search_by_description(self):
        registry = _make_registry()
        results = registry.search_tools("field")
        names = [r["name"] for r in results]
        assert "add_field" in names

    def test_search_returns_full_schema(self):
        registry = _make_registry()
        results = registry.search_tools("sync")
        assert len(results) > 0
        schema = results[0]
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"

    def test_search_no_match(self):
        registry = _make_registry()
        results = registry.search_tools("nonexistent_xyz")
        assert results == []

    def test_search_includes_deferred_only(self):
        """Non-deferred tool 'search_code' must NOT appear even though 'search' is in its name."""
        registry = _make_registry()
        results = registry.search_tools("search")
        names = [r["name"] for r in results]
        assert "search_code" not in names


class TestExistingMethodsUnchanged:
    """Verify existing ToolRegistry methods still work after extension."""

    def test_register_and_get(self):
        registry = _make_registry()
        tool = registry.get("read_file")
        assert tool is not None
        assert tool.meta.name == "read_file"
        assert registry.get("nonexistent") is None

    def test_get_deferred(self):
        registry = _make_registry()
        deferred = registry.get_deferred()
        assert set(deferred) == {"sync_now", "add_field"}

    def test_get_read_only(self):
        registry = _make_registry()
        ro = registry.get_read_only()
        names = [t.meta.name for t in ro]
        assert set(names) == {"read_file", "search_code"}
