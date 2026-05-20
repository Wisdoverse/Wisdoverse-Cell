"""SQLAlchemy adapter for control-plane work-item persistence."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .company_store import SqlAlchemyControlPlaneCompanyStore
from .goal_store import SqlAlchemyControlPlaneGoalStore
from .models import AuditEvent, CompanyContext, WorkItem
from .store_utils import model_values, now_utc
from .tables import AuditEventTable, CompanyContextTable, GoalTable, WorkItemTable
from .work_item_ports import ControlPlaneWorkItemStore


class SqlAlchemyControlPlaneWorkItemStore(ControlPlaneWorkItemStore):
    """Session-scoped control-plane work-item store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._goals = SqlAlchemyControlPlaneGoalStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await self._companies.get_company(company_id)

    async def get_goal(self, goal_id: str) -> GoalTable | None:
        return await self._goals.get_goal(goal_id)

    async def create_work_item(self, work_item: WorkItem) -> WorkItemTable:
        row = WorkItemTable(**model_values(work_item))
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_work_item(self, work_item_id: str) -> WorkItemTable | None:
        result = await self._session.execute(
            select(WorkItemTable).where(WorkItemTable.work_item_id == work_item_id)
        )
        return result.scalar_one_or_none()

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
    ) -> list[WorkItemTable]:
        query = select(WorkItemTable).where(WorkItemTable.company_id == company_id)
        if status:
            query = query.where(WorkItemTable.status == status)
        if priority:
            query = query.where(WorkItemTable.priority == priority)
        if goal_id:
            query = query.where(WorkItemTable.goal_id == goal_id)
        if owner_agent_id:
            query = query.where(WorkItemTable.owner_agent_id == owner_agent_id)
        if owner_user_id:
            query = query.where(WorkItemTable.owner_user_id == owner_user_id)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    WorkItemTable.title.ilike(pattern),
                    WorkItemTable.description.ilike(pattern),
                    WorkItemTable.external_ref.ilike(pattern),
                )
            )
        result = await self._session.execute(
            query.order_by(WorkItemTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_work_item_status(
        self,
        work_item_id: str,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> WorkItemTable | None:
        row = await self.get_work_item(work_item_id)
        if row is None:
            return None
        row.status = status
        if owner_agent_id is not None:
            row.owner_agent_id = owner_agent_id
        if owner_user_id is not None:
            row.owner_user_id = owner_user_id
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await self._companies.append_audit_event(event)
