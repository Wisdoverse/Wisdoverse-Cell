"""SQLAlchemy adapter for control-plane decision persistence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import AgentRunId, CompanyId, DecisionId, GoalId, WorkItemId

from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .decision_ports import ControlPlaneDecisionStore
from .domain_records import decision_record
from .goal_store import SqlAlchemyControlPlaneGoalStore
from .models import AgentRun, AuditEvent, CompanyContext, Decision, Goal, WorkItem
from .store_utils import model_values, now_utc
from .tables import DecisionTable
from .work_item_store import SqlAlchemyControlPlaneWorkItemStore


class SqlAlchemyControlPlaneDecisionStore(ControlPlaneDecisionStore):
    """Session-scoped control-plane decision store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._runs = SqlAlchemyControlPlaneAgentRunStore(session)
        self._goals = SqlAlchemyControlPlaneGoalStore(session)
        self._work_items = SqlAlchemyControlPlaneWorkItemStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        return await self._companies.get_company(company_id)

    async def get_agent_run(self, run_id: AgentRunId) -> AgentRun | None:
        return await self._runs.get_agent_run(run_id)

    async def get_goal(self, goal_id: GoalId) -> Goal | None:
        return await self._goals.get_goal(goal_id)

    async def get_work_item(self, work_item_id: WorkItemId) -> WorkItem | None:
        return await self._work_items.get_work_item(work_item_id)

    async def create_decision(self, decision: Decision) -> Decision:
        row = DecisionTable(**model_values(decision))
        self._session.add(row)
        await self._session.flush()
        return decision_record(row)

    async def get_decision(self, decision_id: DecisionId) -> Decision | None:
        row = await self._get_decision_row(decision_id)
        return decision_record(row) if row is not None else None

    async def _get_decision_row(self, decision_id: DecisionId) -> DecisionTable | None:
        result = await self._session.execute(
            select(DecisionTable).where(DecisionTable.decision_id == decision_id)
        )
        return result.scalar_one_or_none()

    async def list_decisions(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Decision]:
        query = select(DecisionTable).where(DecisionTable.company_id == company_id)
        if status:
            query = query.where(DecisionTable.status == status)
        if run_id:
            query = query.where(DecisionTable.run_id == run_id)
        elif run_ids:
            query = query.where(DecisionTable.run_id.in_(run_ids))
        if goal_id:
            query = query.where(DecisionTable.goal_id == goal_id)
        if work_item_id:
            query = query.where(DecisionTable.work_item_id == work_item_id)
        result = await self._session.execute(
            query.order_by(DecisionTable.created_at.desc()).limit(limit)
        )
        return [decision_record(row) for row in result.scalars().all()]

    async def update_decision_status(
        self,
        decision_id: DecisionId,
        *,
        status: str,
        selected_option: str | None = None,
        decided_by: str | None = None,
    ) -> Decision | None:
        row = await self._get_decision_row(decision_id)
        if row is None:
            return None
        row.status = status
        if selected_option is not None:
            row.selected_option = selected_option
        if decided_by is not None:
            row.decided_by = decided_by
        row.updated_at = now_utc()
        await self._session.flush()
        return decision_record(row)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._companies.append_audit_event(event)
