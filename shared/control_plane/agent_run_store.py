"""SQLAlchemy adapter for control-plane agent run persistence."""
from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_run_ports import ControlPlaneAgentRunStore
from .domain.agent_run_lifecycle import TERMINAL_STATUSES as AGENT_RUN_TERMINAL_STATUSES
from .domain_records import agent_run_record
from .models import AgentRun, AgentRunStatus
from .store_utils import model_values, now_utc
from .tables import AgentRunTable


class SqlAlchemyControlPlaneAgentRunStore(ControlPlaneAgentRunStore):
    """Session-scoped control-plane agent run store."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_agent_run(self, run: AgentRun) -> AgentRun:
        row = AgentRunTable(**model_values(run))
        self._session.add(row)
        await self._session.flush()
        return agent_run_record(row)

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        row = await self._get_agent_run_row(run_id)
        return agent_run_record(row) if row is not None else None

    async def _get_agent_run_row(self, run_id: str) -> AgentRunTable | None:
        result = await self._session.execute(
            select(AgentRunTable).where(AgentRunTable.run_id == run_id)
        )
        return result.scalar_one_or_none()

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
    ) -> list[AgentRun]:
        query = select(AgentRunTable).where(AgentRunTable.company_id == company_id)
        if status:
            query = query.where(AgentRunTable.status == status)
        if agent_id:
            query = query.where(AgentRunTable.agent_id == agent_id)
        if trace_id:
            query = query.where(AgentRunTable.trace_id == trace_id)
        if goal_id:
            query = query.where(AgentRunTable.goal_id == goal_id)
        if work_item_id:
            query = query.where(AgentRunTable.work_item_id == work_item_id)
        result = await self._session.execute(
            query.order_by(AgentRunTable.started_at.desc()).limit(limit)
        )
        return [agent_run_record(row) for row in result.scalars().all()]

    async def update_agent_run_status(
        self,
        run_id: str,
        status: AgentRunStatus | str,
        *,
        error_category: str | None = None,
        error_message: str | None = None,
        last_successful_step: str | None = None,
        output_events: list[dict[str, Any]] | None = None,
        cost_usd: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> AgentRun | None:
        row = await self._get_agent_run_row(run_id)
        if row is None:
            return None
        status_value = status.value if isinstance(status, Enum) else status
        row.status = status_value
        if status_value in {s.value for s in AGENT_RUN_TERMINAL_STATUSES}:
            row.completed_at = now_utc()
        if error_category is not None:
            row.error_category = error_category
        if error_message is not None:
            row.error_message = error_message
        if last_successful_step is not None:
            row.last_successful_step = last_successful_step
        if output_events is not None:
            row.output_events = output_events
        if cost_usd is not None:
            row.cost_usd = cost_usd
        if input_tokens is not None:
            row.input_tokens = input_tokens
        if output_tokens is not None:
            row.output_tokens = output_tokens
        await self._session.flush()
        return agent_run_record(row)

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> AgentRun | None:
        row = await self._get_agent_run_row(run_id)
        if row is None:
            return None
        row.cost_usd = float(row.cost_usd or 0.0) + cost_usd
        row.input_tokens = int(row.input_tokens or 0) + input_tokens
        row.output_tokens = int(row.output_tokens or 0) + output_tokens
        await self._session.flush()
        return agent_run_record(row)
