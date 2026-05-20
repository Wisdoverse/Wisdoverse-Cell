"""SQLAlchemy adapter for control-plane artifact persistence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .artifact_ports import ControlPlaneArtifactStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .goal_store import SqlAlchemyControlPlaneGoalStore
from .models import Artifact, AuditEvent, CompanyContext
from .store_utils import model_values
from .tables import (
    AgentRunTable,
    ArtifactTable,
    AuditEventTable,
    CompanyContextTable,
    GoalTable,
    WorkItemTable,
)
from .work_item_store import SqlAlchemyControlPlaneWorkItemStore


class SqlAlchemyControlPlaneArtifactStore(ControlPlaneArtifactStore):
    """Session-scoped control-plane artifact store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._runs = SqlAlchemyControlPlaneAgentRunStore(session)
        self._goals = SqlAlchemyControlPlaneGoalStore(session)
        self._work_items = SqlAlchemyControlPlaneWorkItemStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await self._companies.get_company(company_id)

    async def get_agent_run(self, run_id: str) -> AgentRunTable | None:
        return await self._runs.get_agent_run(run_id)

    async def get_goal(self, goal_id: str) -> GoalTable | None:
        return await self._goals.get_goal(goal_id)

    async def get_work_item(self, work_item_id: str) -> WorkItemTable | None:
        return await self._work_items.get_work_item(work_item_id)

    async def create_artifact(self, artifact: Artifact) -> ArtifactTable:
        row = ArtifactTable(**model_values(artifact))
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_artifact(self, artifact_id: str) -> ArtifactTable | None:
        result = await self._session.execute(
            select(ArtifactTable).where(ArtifactTable.artifact_id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def list_artifacts(
        self,
        *,
        company_id: str,
        artifact_type: str | None = None,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = 50,
    ) -> list[ArtifactTable]:
        query = select(ArtifactTable).where(ArtifactTable.company_id == company_id)
        if artifact_type:
            query = query.where(ArtifactTable.artifact_type == artifact_type)
        if run_id:
            query = query.where(ArtifactTable.run_id == run_id)
        elif run_ids:
            query = query.where(ArtifactTable.run_id.in_(run_ids))
        if goal_id:
            query = query.where(ArtifactTable.goal_id == goal_id)
        if work_item_id:
            query = query.where(ArtifactTable.work_item_id == work_item_id)
        if created_by_agent_id:
            query = query.where(ArtifactTable.created_by_agent_id == created_by_agent_id)
        result = await self._session.execute(
            query.order_by(ArtifactTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await self._companies.append_audit_event(event)
