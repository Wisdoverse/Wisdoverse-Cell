"""SQLAlchemy adapter for control-plane goal persistence."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import CompanyId, GoalId

from .company_store import SqlAlchemyControlPlaneCompanyStore
from .domain_records import goal_record
from .goal_ports import ControlPlaneGoalStore
from .models import AuditEvent, CompanyContext, Goal
from .store_utils import model_values, now_utc
from .tables import GoalTable


class SqlAlchemyControlPlaneGoalStore(ControlPlaneGoalStore):
    """Session-scoped control-plane goal store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        return await self._companies.get_company(company_id)

    async def create_goal(self, goal: Goal) -> Goal:
        row = GoalTable(**model_values(goal))
        self._session.add(row)
        await self._session.flush()
        return goal_record(row)

    async def get_goal(self, goal_id: GoalId) -> Goal | None:
        row = await self._get_goal_row(goal_id)
        return goal_record(row) if row is not None else None

    async def _get_goal_row(self, goal_id: GoalId) -> GoalTable | None:
        result = await self._session.execute(
            select(GoalTable).where(GoalTable.goal_id == goal_id)
        )
        return result.scalar_one_or_none()

    async def list_goals(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Goal]:
        query = select(GoalTable).where(GoalTable.company_id == company_id)
        if status:
            query = query.where(GoalTable.status == status)
        if owner_agent_id:
            query = query.where(GoalTable.owner_agent_id == owner_agent_id)
        if owner_user_id:
            query = query.where(GoalTable.owner_user_id == owner_user_id)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    GoalTable.title.ilike(pattern),
                    GoalTable.description.ilike(pattern),
                    GoalTable.success_metric.ilike(pattern),
                )
            )
        result = await self._session.execute(
            query.order_by(GoalTable.created_at.desc()).limit(limit)
        )
        return [goal_record(row) for row in result.scalars().all()]

    async def update_goal_status(
        self,
        goal_id: GoalId,
        *,
        status: str,
        current_value: float | None = None,
    ) -> Goal | None:
        row = await self._get_goal_row(goal_id)
        if row is None:
            return None
        row.status = status
        if current_value is not None:
            row.current_value = current_value
        row.updated_at = now_utc()
        await self._session.flush()
        return goal_record(row)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._companies.append_audit_event(event)
