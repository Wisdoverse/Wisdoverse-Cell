"""SQLAlchemy adapter for control-plane artifact persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .artifact_ports import ControlPlaneArtifactStore
from .models import Artifact, AuditEvent, CompanyContext
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneArtifactStore(ControlPlaneArtifactStore):
    """Session-scoped control-plane artifact store."""

    def __init__(self, session: AsyncSession):
        self._artifacts = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._artifacts.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._artifacts.get_company(company_id)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._artifacts.get_agent_run(run_id)

    async def get_goal(self, goal_id: str) -> Any | None:
        return await self._artifacts.get_goal(goal_id)

    async def get_work_item(self, work_item_id: str) -> Any | None:
        return await self._artifacts.get_work_item(work_item_id)

    async def create_artifact(self, artifact: Artifact) -> Any:
        return await self._artifacts.create_artifact(artifact)

    async def get_artifact(self, artifact_id: str) -> Any | None:
        return await self._artifacts.get_artifact(artifact_id)

    async def list_artifacts(
        self,
        *,
        company_id: str,
        artifact_type: str | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._artifacts.list_artifacts(
            company_id=company_id,
            artifact_type=artifact_type,
            run_id=run_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            created_by_agent_id=created_by_agent_id,
            limit=limit,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._artifacts.append_audit_event(event)
