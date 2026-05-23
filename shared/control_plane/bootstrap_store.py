"""SQLAlchemy adapter for control-plane role bootstrap persistence."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import CompanyId

from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .bootstrap_ports import ControlPlaneRoleBootstrapStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .models import AgentRole, AuditEvent, CompanyContext


class SqlAlchemyControlPlaneRoleBootstrapStore(ControlPlaneRoleBootstrapStore):
    """Session-scoped store for idempotent role bootstrap writes."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._roles = SqlAlchemyControlPlaneAgentRegistryStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        return await self._companies.get_company(company_id)

    async def create_company_if_absent(
        self, company: CompanyContext
    ) -> CompanyContext | None:
        try:
            async with self._session.begin_nested():
                return await self._companies.create_company(company)
        except IntegrityError:
            return None

    async def get_agent_role(
        self,
        *,
        company_id: CompanyId,
        agent_id: str,
    ) -> AgentRole | None:
        return await self._roles.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def create_agent_role_if_absent(self, role: AgentRole) -> AgentRole | None:
        try:
            async with self._session.begin_nested():
                return await self._roles.create_agent_role(role)
        except IntegrityError:
            return None

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._audits.append_audit_event(event)
