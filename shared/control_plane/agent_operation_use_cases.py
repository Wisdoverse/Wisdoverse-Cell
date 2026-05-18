"""Application use cases for control-plane agent operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_operation_ports import ControlPlaneAgentOperationStore
from .agent_runner import AgentWakeupResult, ControlPlaneAgentRunner
from .scheduler import AgentHeartbeatResult, ControlPlaneHeartbeatScheduler


class AgentDefinitionNotFoundError(Exception):
    """Raised when a persisted agent definition cannot be found."""


class AgentOperationCompanyNotFoundError(Exception):
    """Raised when a scheduler target company cannot be found."""


@dataclass(frozen=True, slots=True)
class AgentWakeupUseCaseResult:
    """Result of waking a persisted agent definition."""

    run: Any | None
    wakeup: AgentWakeupResult


async def wake_agent_definition(
    store: ControlPlaneAgentOperationStore,
    *,
    company_id: str,
    agent_id: str,
    input_payload: dict[str, Any] | None = None,
    actor_id: str = "api",
    trace_id: str | None = None,
    goal_id: str | None = None,
    work_item_id: str | None = None,
) -> AgentWakeupUseCaseResult:
    """Wake a persisted agent definition through its configured adapter."""
    agent = await store.get_agent_role(company_id=company_id, agent_id=agent_id)
    if agent is None:
        raise AgentDefinitionNotFoundError(agent_id)

    wakeup = await ControlPlaneAgentRunner(store).wake(
        agent,
        input_payload=input_payload,
        actor_id=actor_id,
        trace_id=trace_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
    )
    return AgentWakeupUseCaseResult(
        run=await store.get_agent_run(wakeup.run_id),
        wakeup=wakeup,
    )


async def run_heartbeat_scheduler_once(
    store: ControlPlaneAgentOperationStore,
    *,
    company_id: str,
    limit: int = 500,
) -> list[AgentHeartbeatResult]:
    """Run due heartbeat wakeups for one company."""
    if await store.get_company(company_id) is None:
        raise AgentOperationCompanyNotFoundError(company_id)
    return await ControlPlaneHeartbeatScheduler(store).run_due_once(
        company_id=company_id,
        limit=limit,
    )
