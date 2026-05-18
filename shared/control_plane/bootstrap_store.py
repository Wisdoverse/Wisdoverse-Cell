"""SQLAlchemy adapter for control-plane role bootstrap persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .bootstrap_ports import ControlPlaneRoleBootstrapStore
from .models import AgentRole, AuditEvent, CompanyContext
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneRoleBootstrapStore(ControlPlaneRoleBootstrapStore):
    """Session-scoped store for idempotent role bootstrap writes."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._roles = ControlPlaneRepository(session)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._roles.get_company(company_id)

    async def create_company_if_absent(self, company: CompanyContext) -> Any | None:
        try:
            async with self._session.begin_nested():
                return await self._roles.create_company(company)
        except IntegrityError:
            return None

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        return await self._roles.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def create_agent_role_if_absent(self, role: AgentRole) -> Any | None:
        try:
            async with self._session.begin_nested():
                return await self._roles.create_agent_role(role)
        except IntegrityError:
            return None

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._roles.append_audit_event(event)
