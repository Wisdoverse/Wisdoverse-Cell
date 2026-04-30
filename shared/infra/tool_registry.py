"""Unified Tool interface and registry for Wisdoverse Cell.

All external capabilities (Feishu API, OP API, LLM, Git, etc.) implement
the Tool interface. ToolRegistry provides global capability discovery.
Coordinator uses it to assign tools per agent per task.

Design principle: fail-closed defaults via build_tool().
"""
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel

from shared.schemas.coordinator import DispatchPermissions


class ToolMeta(BaseModel):
    """Tool metadata with fail-closed defaults."""

    name: str
    description: str
    is_read_only: bool = False
    is_concurrency_safe: bool = False
    is_destructive: bool = False
    should_defer: bool = False
    requires_approval: bool = False


class ToolContext(BaseModel):
    """Execution context passed to tools."""

    agent_id: str
    task_id: str | None = None
    workflow_id: str | None = None
    trace_id: str | None = None


class ToolResult(BaseModel):
    """Standard tool execution result."""

    success: bool
    data: dict[str, Any] = {}
    error: str | None = None


class Tool(ABC):
    """Base class for all tools."""

    meta: ToolMeta

    @abstractmethod
    async def execute(self, input: dict, context: ToolContext) -> ToolResult:
        ...


class _FunctionalTool(Tool):
    """Tool backed by an async handler function (created by build_tool)."""

    def __init__(self, meta: ToolMeta, handler: Callable[..., Coroutine]):
        self.meta = meta
        self._handler = handler

    async def execute(self, input: dict, context: ToolContext) -> ToolResult:
        return await self._handler(input, context)


def build_tool(
    name: str,
    description: str,
    handler: Callable[..., Coroutine],
    *,
    is_read_only: bool = False,
    is_concurrency_safe: bool = False,
    is_destructive: bool = False,
    should_defer: bool = False,
    requires_approval: bool = False,
) -> Tool:
    """Factory: create a Tool with fail-closed defaults."""
    meta = ToolMeta(
        name=name,
        description=description,
        is_read_only=is_read_only,
        is_concurrency_safe=is_concurrency_safe,
        is_destructive=is_destructive,
        should_defer=should_defer,
        requires_approval=requires_approval,
    )
    return _FunctionalTool(meta=meta, handler=handler)


class ToolRegistry:
    """Global tool registry. Coordinator queries this to discover capabilities."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._raw_schemas: dict[str, dict] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.meta.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_for_agent(
        self,
        agent_id: str,
        permissions: DispatchPermissions | None = None,
    ) -> list[Tool]:
        """Return tools available to an agent, filtered by permissions."""
        tools = list(self._tools.values())
        if permissions:
            if permissions.allowed_tools is not None:
                allowed = set(permissions.allowed_tools)
                tools = [t for t in tools if t.meta.name in allowed]
            denied = set(permissions.denied_tools)
            tools = [t for t in tools if t.meta.name not in denied]
        return tools

    def get_read_only(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.meta.is_read_only]

    def get_deferred(self) -> list[str]:
        return [t.meta.name for t in self._tools.values() if t.meta.should_defer]

    def register_raw_schema(self, name: str, schema: dict) -> None:
        """Store the original Anthropic-format schema dict for a tool."""
        self._raw_schemas[name] = schema

    # -- Deferred tool loading extensions --

    def _tool_to_anthropic_schema(self, tool: Tool) -> dict:
        """Convert a Tool to Anthropic API tool-definition format.

        Returns the raw schema if registered, otherwise a minimal stub.
        """
        if tool.meta.name in self._raw_schemas:
            return self._raw_schemas[tool.meta.name]
        return {
            "name": tool.meta.name,
            "description": tool.meta.description,
            "input_schema": {"type": "object", "properties": {}},
        }

    def to_anthropic_schemas(
        self, active_deferred: set[str] | None = None,
    ) -> list[dict]:
        """Build tool schemas for the Anthropic API.

        - Non-deferred tools: full schema via ``_tool_to_anthropic_schema``.
        - Deferred tools in *active_deferred*: full schema (loaded by search).
        - Other deferred tools: lightweight stub.
        - ``tool_search`` meta-tool is always appended last.
        """
        active = active_deferred or set()
        schemas: list[dict] = []
        for tool in self._tools.values():
            if not tool.meta.should_defer or tool.meta.name in active:
                schemas.append(self._tool_to_anthropic_schema(tool))
            else:
                schemas.append({
                    "name": tool.meta.name,
                    "description": tool.meta.description,
                    "input_schema": {"type": "object", "properties": {}},
                })
        schemas.append(self.tool_search_schema())
        return schemas

    def search_tools(self, query: str) -> list[dict]:
        """Search deferred tools by name or description (case-insensitive substring).

        Returns Anthropic schemas for matches (raw schema if registered).
        """
        q = query.lower()
        results: list[dict] = []
        for tool in self._tools.values():
            if not tool.meta.should_defer:
                continue
            if q in tool.meta.name.lower() or q in tool.meta.description.lower():
                results.append(self._tool_to_anthropic_schema(tool))
        return results

    @staticmethod
    def tool_search_schema() -> dict:
        """Return the ``tool_search`` meta-tool definition."""
        return {
            "name": "tool_search",
            "description": "搜索可用的额外工具。输入关键词，返回匹配工具的完整定义。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（工具名称或描述）",
                    },
                },
                "required": ["query"],
            },
        }
