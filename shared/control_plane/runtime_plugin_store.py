"""SQLAlchemy adapter for the control-plane runtime plugin."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .artifact_store import SqlAlchemyControlPlaneArtifactStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .bootstrap import (
    ensure_core_organization_role_agents,
    ensure_core_runtime_agent_roles,
)
from .bootstrap_store import SqlAlchemyControlPlaneRoleBootstrapStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .models import AgentRun, ApprovalRequest, Artifact, AuditEvent, BudgetUsage, CompanyContext
from .runtime_plugin_ports import ControlPlaneRuntimePluginStore


class SqlAlchemyControlPlaneRuntimePluginStore(ControlPlaneRuntimePluginStore):
    """Session-scoped runtime plugin store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._agent_runs = SqlAlchemyControlPlaneAgentRunStore(session)
        self._approvals = SqlAlchemyControlPlaneApprovalStore(session)
        self._budgets = SqlAlchemyControlPlaneBudgetStore(session)
        self._artifacts = SqlAlchemyControlPlaneArtifactStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def get_company(self, company_id: str) -> CompanyContext | None:
        return await self._companies.get_company(company_id)

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        return await self._companies.create_company(company)

    async def create_agent_run(self, run: AgentRun) -> AgentRun:
        return await self._agent_runs.create_agent_run(run)

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        return await self._agent_runs.get_agent_run(run_id)

    async def update_agent_run_status(
        self,
        run_id: str,
        status: Any,
        **values: Any,
    ) -> AgentRun | None:
        return await self._agent_runs.update_agent_run_status(
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
    ) -> list[ApprovalRequest]:
        return await self._approvals.list_approvals(
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
    ) -> list[BudgetUsage]:
        return await self._budgets.list_budget_usage(
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
    ) -> list[AuditEvent]:
        return await self._audits.list_audit_events(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        return await self._artifacts.create_artifact(artifact)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._audits.append_audit_event(event)

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
