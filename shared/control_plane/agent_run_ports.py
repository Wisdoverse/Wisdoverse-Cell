"""Ports for control-plane agent run read persistence."""
from __future__ import annotations

from typing import Any, Protocol


class ControlPlaneAgentRunStore(Protocol):
    """Persistence operations required by agent-run query use cases."""

    async def get_agent_run(self, run_id: str) -> Any | None:
        """Return one agent run by id."""

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        status: str | None = None,
        agent_id: str | None = None,
        trace_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return agent runs for one company."""
