"""Application query use cases for control-plane agent runs."""
from __future__ import annotations

from typing import Any

from .agent_run_ports import ControlPlaneAgentRunStore


class AgentRunNotFoundError(Exception):
    """Raised when an agent run cannot be found."""


async def list_agent_runs(
    store: ControlPlaneAgentRunStore,
    *,
    company_id: str,
    status: str | None = None,
    agent_id: str | None = None,
    trace_id: str | None = None,
    goal_id: str | None = None,
    work_item_id: str | None = None,
    limit: int = 50,
) -> list[Any]:
    """List control-plane agent runs."""
    return await store.list_agent_runs(
        company_id=company_id,
        status=status,
        agent_id=agent_id,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        limit=limit,
    )


async def get_agent_run(
    store: ControlPlaneAgentRunStore,
    *,
    run_id: str,
) -> Any:
    """Return one control-plane agent run or raise not found."""
    row = await store.get_agent_run(run_id)
    if row is None:
        raise AgentRunNotFoundError(run_id)
    return row
