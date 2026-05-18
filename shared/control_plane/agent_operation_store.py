"""SQLAlchemy adapter for control-plane agent execution operations."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_operation_ports import ControlPlaneAgentOperationStore
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneAgentOperationStore(ControlPlaneAgentOperationStore):
    """Session-scoped store for wakeup and heartbeat operations."""

    def __init__(self, session: AsyncSession):
        self._operations = ControlPlaneRepository(session)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._operations.get_company(company_id)

    async def get_agent_role(self, *, company_id: str, agent_id: str) -> Any | None:
        return await self._operations.get_agent_role(
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
        return await self._operations.list_agent_roles(
            company_id=company_id,
            status=status,
            limit=limit,
        )

    async def create_agent_run(self, run: Any) -> Any:
        return await self._operations.create_agent_run(run)

    async def get_agent_run(self, run_id: str) -> Any | None:
        return await self._operations.get_agent_run(run_id)

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._operations.list_agent_runs(
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
        return await self._operations.update_agent_run_status(
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
        return await self._operations.list_approvals(
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
        return await self._operations.list_budget_usage(
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
        return await self._operations.list_audit_events(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )

    async def create_artifact(self, artifact: Any) -> Any:
        return await self._operations.create_artifact(artifact)

    async def append_audit_event(self, event: Any) -> Any:
        return await self._operations.append_audit_event(event)
