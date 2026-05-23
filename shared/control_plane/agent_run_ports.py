"""Ports for control-plane agent run read persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import AgentRunId, CompanyId

from .models import AgentRun


class ControlPlaneAgentRunStore(Protocol):
    """Persistence operations required by agent-run query use cases.

    `run_id` and `company_id` parameters use the `AgentRunId` and
    `CompanyId` `NewType`s from `shared.core.identifiers` (DDD-007
    adoption).
    """

    async def get_agent_run(self, run_id: AgentRunId) -> AgentRun | None:
        """Return one agent run by typed identifier."""

    async def list_agent_runs(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        agent_id: str | None = None,
        trace_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        """Return agent runs scoped to one typed CompanyId."""
