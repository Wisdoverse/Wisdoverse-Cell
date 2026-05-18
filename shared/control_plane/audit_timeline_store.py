"""SQLAlchemy adapter for control-plane audit and timeline queries."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .audit_timeline_ports import ControlPlaneAuditTimelineStore
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneAuditTimelineStore(ControlPlaneAuditTimelineStore):
    """Session-scoped audit and timeline query store."""

    def __init__(self, session: AsyncSession):
        self._activity = ControlPlaneRepository(session)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._activity.get_agent_run(run_id)

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._activity.list_agent_runs(
            company_id=company_id,
            trace_id=trace_id,
            limit=limit,
        )

    async def list_audit_events(
        self,
        *,
        company_id: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._activity.list_audit_events(
            company_id=company_id,
            trace_id=trace_id,
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
        )

    async def list_approvals(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._activity.list_approvals(
            company_id=company_id,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._activity.list_budget_usage(
            company_id=company_id,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )

    async def list_decisions(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._activity.list_decisions(
            company_id=company_id,
            run_id=run_id,
            run_ids=run_ids,
            limit=limit,
        )

    async def list_artifacts(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._activity.list_artifacts(
            company_id=company_id,
            run_id=run_id,
            run_ids=run_ids,
            limit=limit,
        )
