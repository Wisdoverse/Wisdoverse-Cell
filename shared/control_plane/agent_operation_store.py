"""SQLAlchemy adapter for control-plane agent execution operations."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_operation_ports import ControlPlaneAgentOperationStore
from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore
from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .artifact_store import SqlAlchemyControlPlaneArtifactStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .company_store import SqlAlchemyControlPlaneCompanyStore


class SqlAlchemyControlPlaneAgentOperationStore(ControlPlaneAgentOperationStore):
    """Session-scoped store for wakeup and heartbeat operations."""

    def __init__(self, session: AsyncSession):
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._agents = SqlAlchemyControlPlaneAgentRegistryStore(session)
        self._agent_runs = SqlAlchemyControlPlaneAgentRunStore(session)
        self._approvals = SqlAlchemyControlPlaneApprovalStore(session)
        self._budgets = SqlAlchemyControlPlaneBudgetStore(session)
        self._artifacts = SqlAlchemyControlPlaneArtifactStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._companies.get_company(company_id)

    async def get_agent_role(self, *, company_id: str, agent_id: str) -> Any | None:
        return await self._agents.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._agents.list_agent_roles(
            company_id=company_id,
            status=status,
            limit=limit,
        )

    async def create_agent_run(self, run: Any) -> Any:
        return await self._agent_runs.create_agent_run(run)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._agent_runs.get_agent_run(run_id)

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._agent_runs.list_agent_runs(
            company_id=company_id,
            agent_id=agent_id,
            limit=limit,
        )

    async def update_agent_run_status(
        self,
        run_id: str,
        status: Any,
        **values: Any,
    ) -> Any | None:
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
    ) -> list[Any]:
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
    ) -> list[Any]:
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
    ) -> list[Any]:
        return await self._audits.list_audit_events(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )

    async def create_artifact(self, artifact: Any) -> Any:
        return await self._artifacts.create_artifact(artifact)

    async def append_audit_event(self, event: Any) -> Any:
        return await self._audits.append_audit_event(event)
