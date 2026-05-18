"""SQLAlchemy adapter for control-plane agent run reads."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_run_ports import ControlPlaneAgentRunStore
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneAgentRunStore(ControlPlaneAgentRunStore):
    """Session-scoped control-plane agent run store."""

    def __init__(self, session: AsyncSession):
        self._runs = ControlPlaneRepository(session)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._runs.get_agent_run(run_id)

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
        return await self._runs.list_agent_runs(
            company_id=company_id,
            status=status,
            agent_id=agent_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )
