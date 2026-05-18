"""SQLAlchemy adapter for control-plane work-item persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent, CompanyContext, WorkItem
from .repository import ControlPlaneRepository
from .work_item_ports import ControlPlaneWorkItemStore


class SqlAlchemyControlPlaneWorkItemStore(ControlPlaneWorkItemStore):
    """Session-scoped control-plane work-item store."""

    def __init__(self, session: AsyncSession):
        self._work_items = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._work_items.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._work_items.get_company(company_id)

    async def get_goal(self, goal_id: str) -> Any | None:
        return await self._work_items.get_goal(goal_id)

    async def create_work_item(self, work_item: WorkItem) -> Any:
        return await self._work_items.create_work_item(work_item)

    async def get_work_item(self, work_item_id: str) -> Any | None:
        return await self._work_items.get_work_item(work_item_id)

    async def list_work_items(
        self,
        *,
        company_id: str,
        status: str | None = None,
        priority: str | None = None,
        goal_id: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._work_items.list_work_items(
            company_id=company_id,
            status=status,
            priority=priority,
            goal_id=goal_id,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )

    async def update_work_item_status(
        self,
        work_item_id: str,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> Any | None:
        return await self._work_items.update_work_item_status(
            work_item_id,
            status=status,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._work_items.append_audit_event(event)
