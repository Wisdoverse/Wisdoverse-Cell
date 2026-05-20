"""SQLAlchemy adapter for control-plane audit and timeline queries."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .artifact_store import SqlAlchemyControlPlaneArtifactStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .audit_timeline_ports import ControlPlaneAuditTimelineStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .decision_store import SqlAlchemyControlPlaneDecisionStore


class SqlAlchemyControlPlaneAuditTimelineStore(ControlPlaneAuditTimelineStore):
    """Session-scoped audit and timeline query store."""

    def __init__(self, session: AsyncSession):
        self._agent_runs = SqlAlchemyControlPlaneAgentRunStore(session)
        self._approvals = SqlAlchemyControlPlaneApprovalStore(session)
        self._artifacts = SqlAlchemyControlPlaneArtifactStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)
        self._budgets = SqlAlchemyControlPlaneBudgetStore(session)
        self._decisions = SqlAlchemyControlPlaneDecisionStore(session)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._agent_runs.get_agent_run(run_id)

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._agent_runs.list_agent_runs(
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
        return await self._audits.list_audit_events(
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
        return await self._approvals.list_approvals(
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
        return await self._budgets.list_budget_usage(
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
        return await self._decisions.list_decisions(
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
        return await self._artifacts.list_artifacts(
            company_id=company_id,
            run_id=run_id,
            run_ids=run_ids,
            limit=limit,
        )
