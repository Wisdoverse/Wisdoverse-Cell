"""Unified Tool interface and registry for Wisdoverse Cell.

All external capabilities (Feishu API, OP API, LLM, Git, etc.) implement
the Tool interface. ToolRegistry provides global capability discovery.
Coordinator uses it to assign tools per agent per task.

Design principle: fail-closed defaults via build_tool().
"""
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from shared.config import settings
from shared.control_plane.context import get_current_run_context
from shared.schemas.coordinator import DispatchPermissions
from shared.utils.logger import get_logger

from .budget_events import publish_budget_usage_recorded

logger = get_logger("infra.tool_registry")


@dataclass(frozen=True)
class _ToolBudgetReservation:
    company_id: str
    run_id: str | None
    trace_id: str | None
    budget_id: str | None
    cost_usd: float
    tool_name: str
    source_agent_id: str
    session_provider: Any


class ToolMeta(BaseModel):
    """Tool metadata with fail-closed defaults."""

    name: str
    description: str
    is_read_only: bool = False
    is_concurrency_safe: bool = False
    is_destructive: bool = False
    should_defer: bool = False
    requires_approval: bool = False
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    budget_scope: str | None = None


class ToolContext(BaseModel):
    """Execution context passed to tools."""

    agent_id: str
    approval_id: str | None = None
    task_id: str | None = None
    workflow_id: str | None = None
    trace_id: str | None = None
    company_id: str | None = None
    run_id: str | None = None
    goal_id: str | None = None
    work_item_id: str | None = None
    budget_scope: str | None = None
    budget_scope_id: str | None = None
    budget_period: str | None = None
    control_plane_session_provider: Any = None


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
        await _ensure_tool_approval(self.meta, context)
        reservation = await _check_tool_budget(self.meta, context)
        result = await self._handler(input, context)
        if result.success:
            await _record_tool_budget_usage(reservation)
        return result


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
    estimated_cost_usd: float = 0.0,
    budget_scope: str | None = None,
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
        estimated_cost_usd=estimated_cost_usd,
        budget_scope=budget_scope,
    )
    return _FunctionalTool(meta=meta, handler=handler)


def _tool_budget_enforced() -> bool:
    return getattr(settings, "control_plane_tool_budget_enforced", False) is True


def _approval_enforced() -> bool:
    return getattr(settings, "control_plane_approval_enforced", False) is True


def _tool_requires_approval(meta: ToolMeta) -> bool:
    return meta.requires_approval or meta.is_destructive


async def _ensure_tool_approval(meta: ToolMeta, context: ToolContext) -> None:
    if not _tool_requires_approval(meta):
        return
    if not (settings.control_plane_enabled or _approval_enforced()):
        return

    try:
        from shared.control_plane.approval_gate import ApprovalGateService

        current = get_current_run_context()
        service = ApprovalGateService(
            source_agent_id=context.agent_id,
            session_provider=context.control_plane_session_provider,
            default_company_id=(
                context.company_id
                or (current.company_id if current is not None else None)
                or settings.control_plane_company_id
            ),
            enabled=True,
            enforced=_approval_enforced(),
        )
        await service.ensure_approved_for_sensitive_action(context.approval_id)
    except Exception:
        if _approval_enforced():
            raise
        logger.warning(
            "tool_approval_check_failed",
            tool_name=meta.name,
            agent_id=context.agent_id,
            exc_info=True,
        )


def _resolve_budget_scope_id(scope: str, context: ToolContext) -> str | None:
    if context.budget_scope_id:
        return context.budget_scope_id
    current = get_current_run_context()
    if scope == "agent":
        return context.agent_id
    if scope == "goal":
        return context.goal_id or (current.goal_id if current else None)
    if scope == "work_item":
        return context.work_item_id or (current.work_item_id if current else None)
    return None


async def _check_tool_budget(
    meta: ToolMeta,
    context: ToolContext,
) -> _ToolBudgetReservation | None:
    if meta.estimated_cost_usd <= 0:
        return None

    current = get_current_run_context()
    explicit_company_id = context.company_id or (current.company_id if current else None)
    company_id = explicit_company_id or (
        settings.control_plane_company_id if _tool_budget_enforced() else None
    )
    run_id = context.run_id or (current.run_id if current else None)
    trace_id = context.trace_id or (current.trace_id if current else None)
    if not company_id:
        if _tool_budget_enforced():
            raise ValueError("control_plane_company_id_required_for_tool_budget")
        return None

    scope_value = (
        context.budget_scope
        or meta.budget_scope
        or settings.control_plane_tool_budget_scope
    )
    period_value = context.budget_period or settings.control_plane_tool_budget_period
    scope_id = _resolve_budget_scope_id(scope_value, context)

    try:
        from shared.control_plane.budget_guard import BudgetGuard
        from shared.control_plane.database import control_plane_db_manager
        from shared.control_plane.models import BudgetPeriod, BudgetScope
        from shared.control_plane.repository import ControlPlaneRepository

        session_provider = (
            context.control_plane_session_provider
            or control_plane_db_manager.session
        )
        async with session_provider() as session:
            repo = ControlPlaneRepository(session)
            budget_id: str | None = None
            if _tool_budget_enforced():
                decision = await BudgetGuard(repo).ensure_allowed(
                    company_id=company_id,
                    scope=BudgetScope(scope_value),
                    scope_id=scope_id,
                    period=BudgetPeriod(period_value),
                    estimated_cost_usd=meta.estimated_cost_usd,
                    model=f"tool:{meta.name}",
                )
                budget_id = decision.budget_id
            await session.commit()
            return _ToolBudgetReservation(
                company_id=company_id,
                run_id=run_id,
                trace_id=trace_id,
                budget_id=budget_id,
                cost_usd=meta.estimated_cost_usd,
                tool_name=meta.name,
                source_agent_id=context.agent_id,
                session_provider=session_provider,
            )
    except Exception:
        if _tool_budget_enforced():
            raise
        logger.warning(
            "tool_budget_record_precheck_failed",
            tool_name=meta.name,
            run_id=run_id,
            exc_info=True,
        )
        return None


async def _record_tool_budget_usage(
    reservation: _ToolBudgetReservation | None,
) -> None:
    if reservation is None:
        return
    if reservation.budget_id is None and reservation.run_id is None:
        return

    try:
        from shared.control_plane.budget_guard import BudgetGuard
        from shared.control_plane.repository import ControlPlaneRepository

        budget_event: dict[str, Any] | None = None
        async with reservation.session_provider() as session:
            repo = ControlPlaneRepository(session)
            if reservation.run_id:
                await repo.add_agent_run_usage(
                    reservation.run_id,
                    cost_usd=reservation.cost_usd,
                )
            if reservation.budget_id:
                usage = await BudgetGuard(repo).record_usage(
                    company_id=reservation.company_id,
                    budget_id=reservation.budget_id,
                    cost_usd=reservation.cost_usd,
                    model=f"tool:{reservation.tool_name}",
                    run_id=reservation.run_id,
                    trace_id=reservation.trace_id,
                )
                budget_event = {
                    "company_id": reservation.company_id,
                    "usage_id": usage.usage_id,
                    "budget_id": reservation.budget_id,
                    "cost_usd": reservation.cost_usd,
                    "model": f"tool:{reservation.tool_name}",
                    "source_agent_id": reservation.source_agent_id,
                    "run_id": reservation.run_id,
                    "trace_id": reservation.trace_id,
                }
            await session.commit()
        if budget_event is not None:
            await publish_budget_usage_recorded(**budget_event)
    except Exception:
        if _tool_budget_enforced():
            raise
        logger.warning(
            "tool_budget_usage_record_failed",
            tool_name=reservation.tool_name,
            budget_id=reservation.budget_id,
            exc_info=True,
        )


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
            "description": (
                "Search available deferred tools. Provide a keyword and receive "
                "full schemas for matching tools."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword, matched against tool names or descriptions.",
                    },
                },
                "required": ["query"],
            },
        }
