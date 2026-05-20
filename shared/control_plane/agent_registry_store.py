"""SQLAlchemy adapter for control-plane agent registry persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_registry_ports import ControlPlaneAgentRegistryStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .models import AgentRole, AuditEvent, CompanyContext
from .store_utils import model_values, now_utc, to_db_value
from .tables import AgentRoleTable, AuditEventTable, CompanyContextTable


class SqlAlchemyControlPlaneAgentRegistryStore(ControlPlaneAgentRegistryStore):
    """Session-scoped control-plane agent registry store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await self._companies.get_company(company_id)

    async def create_agent_role(self, role: AgentRole) -> AgentRoleTable:
        row = AgentRoleTable(**model_values(role))
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentRoleTable | None:
        result = await self._session.execute(
            select(AgentRoleTable).where(
                AgentRoleTable.company_id == company_id,
                AgentRoleTable.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

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
    ) -> list[AgentRoleTable]:
        query = select(AgentRoleTable).where(AgentRoleTable.company_id == company_id)
        if status:
            query = query.where(AgentRoleTable.status == status)
        if agent_kind:
            query = query.where(AgentRoleTable.agent_kind == agent_kind)
        if interaction_mode:
            query = query.where(AgentRoleTable.interaction_mode == interaction_mode)
        if adapter_type:
            query = query.where(AgentRoleTable.adapter_type == adapter_type)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    AgentRoleTable.agent_id.ilike(pattern),
                    AgentRoleTable.display_name.ilike(pattern),
                    AgentRoleTable.role.ilike(pattern),
                    AgentRoleTable.title.ilike(pattern),
                )
            )
        result = await self._session.execute(
            query.order_by(AgentRoleTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
        values: dict[str, Any],
    ) -> AgentRoleTable | None:
        row = await self.get_agent_role(company_id=company_id, agent_id=agent_id)
        if row is None:
            return None

        for key, value in values.items():
            db_key = "metadata_json" if key == "metadata" else key
            setattr(row, db_key, to_db_value(value))
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def update_agent_role_status(
        self,
        *,
        company_id: str,
        agent_id: str,
        status: str,
    ) -> AgentRoleTable | None:
        row = await self.get_agent_role(company_id=company_id, agent_id=agent_id)
        if row is None:
            return None
        row.status = status
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await self._audits.append_audit_event(event)
