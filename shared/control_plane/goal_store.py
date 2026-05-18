"""SQLAlchemy adapter for control-plane goal persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .goal_ports import ControlPlaneGoalStore
from .models import AuditEvent, CompanyContext, Goal
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneGoalStore(ControlPlaneGoalStore):
    """Session-scoped control-plane goal store."""

    def __init__(self, session: AsyncSession):
        self._goals = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._goals.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._goals.get_company(company_id)

    async def create_goal(self, goal: Goal) -> Any:
        return await self._goals.create_goal(goal)

    async def get_goal(self, goal_id: str) -> Any | None:
        return await self._goals.get_goal(goal_id)

    async def list_goals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._goals.list_goals(
            company_id=company_id,
            status=status,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )

    async def update_goal_status(
        self,
        goal_id: str,
        *,
        status: str,
        current_value: float | None = None,
    ) -> Any | None:
        return await self._goals.update_goal_status(
            goal_id,
            status=status,
            current_value=current_value,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._goals.append_audit_event(event)
