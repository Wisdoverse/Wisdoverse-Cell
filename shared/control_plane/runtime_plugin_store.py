"""SQLAlchemy adapter for the control-plane runtime plugin."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .bootstrap import (
    ensure_core_organization_role_agents,
    ensure_core_runtime_agent_roles,
)
from .bootstrap_store import SqlAlchemyControlPlaneRoleBootstrapStore
from .models import AgentRun, AuditEvent, CompanyContext
from .repository import ControlPlaneRepository
from .runtime_plugin_ports import ControlPlaneRuntimePluginStore


class SqlAlchemyControlPlaneRuntimePluginStore(ControlPlaneRuntimePluginStore):
    """Session-scoped runtime plugin store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._runtime = ControlPlaneRepository(session)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._runtime.get_company(company_id)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._runtime.create_company(company)

    async def create_agent_run(self, run: AgentRun) -> Any:
        return await self._runtime.create_agent_run(run)

    async def update_agent_run_status(
        self,
        run_id: str,
        status: Any,
        **values: Any,
    ) -> Any | None:
        return await self._runtime.update_agent_run_status(
            run_id,
            status,
            **values,
        )

    async def list_approvals(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._runtime.list_approvals(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._runtime.list_budget_usage(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )

    async def list_audit_events(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._runtime.list_audit_events(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )

    async def create_artifact(self, artifact: Any) -> Any:
        return await self._runtime.create_artifact(artifact)

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._runtime.append_audit_event(event)

    async def ensure_core_organization_role_agents(
        self,
        *,
        company_id: str,
        company_name: str,
    ) -> list[str]:
        return await ensure_core_organization_role_agents(
            SqlAlchemyControlPlaneRoleBootstrapStore(self._session),
            company_id=company_id,
            company_name=company_name,
        )

    async def ensure_core_runtime_agent_roles(
        self,
        *,
        company_id: str,
        company_name: str,
    ) -> list[str]:
        return await ensure_core_runtime_agent_roles(
            SqlAlchemyControlPlaneRoleBootstrapStore(self._session),
            company_id=company_id,
            company_name=company_name,
        )
