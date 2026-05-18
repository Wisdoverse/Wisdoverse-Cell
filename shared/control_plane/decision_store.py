"""SQLAlchemy adapter for control-plane decision persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .decision_ports import ControlPlaneDecisionStore
from .models import AuditEvent, CompanyContext, Decision
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneDecisionStore(ControlPlaneDecisionStore):
    """Session-scoped control-plane decision store."""

    def __init__(self, session: AsyncSession):
        self._decisions = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._decisions.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._decisions.get_company(company_id)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._decisions.get_agent_run(run_id)

    async def get_goal(self, goal_id: str) -> Any | None:
        return await self._decisions.get_goal(goal_id)

    async def get_work_item(self, work_item_id: str) -> Any | None:
        return await self._decisions.get_work_item(work_item_id)

    async def create_decision(self, decision: Decision) -> Any:
        return await self._decisions.create_decision(decision)

    async def get_decision(self, decision_id: str) -> Any | None:
        return await self._decisions.get_decision(decision_id)

    async def list_decisions(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._decisions.list_decisions(
            company_id=company_id,
            status=status,
            run_id=run_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )

    async def update_decision_status(
        self,
        decision_id: str,
        *,
        status: str,
        selected_option: str | None = None,
        decided_by: str | None = None,
    ) -> Any | None:
        return await self._decisions.update_decision_status(
            decision_id,
            status=status,
            selected_option=selected_option,
            decided_by=decided_by,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._decisions.append_audit_event(event)
