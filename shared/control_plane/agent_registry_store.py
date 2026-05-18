"""SQLAlchemy adapter for control-plane agent registry persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_registry_ports import ControlPlaneAgentRegistryStore
from .models import AgentRole, AuditEvent, CompanyContext
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneAgentRegistryStore(ControlPlaneAgentRegistryStore):
    """Session-scoped control-plane agent registry store."""

    def __init__(self, session: AsyncSession):
        self._agents = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._agents.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._agents.get_company(company_id)

    async def create_agent_role(self, role: AgentRole) -> Any:
        return await self._agents.create_agent_role(role)

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        return await self._agents.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        status: str | None = None,
        agent_kind: str | None = None,
        interaction_mode: str | None = None,
        adapter_type: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._agents.list_agent_roles(
            company_id=company_id,
            status=status,
            agent_kind=agent_kind,
            interaction_mode=interaction_mode,
            adapter_type=adapter_type,
            search=search,
            limit=limit,
        )

    async def update_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
        values: dict[str, Any],
    ) -> Any | None:
        return await self._agents.update_agent_role(
            company_id=company_id,
            agent_id=agent_id,
            values=values,
        )

    async def update_agent_role_status(
        self,
        *,
        company_id: str,
        agent_id: str,
        status: str,
    ) -> Any | None:
        return await self._agents.update_agent_role_status(
            company_id=company_id,
            agent_id=agent_id,
            status=status,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._agents.append_audit_event(event)
