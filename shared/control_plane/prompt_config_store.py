"""SQLAlchemy adapter for control-plane agent prompt configuration."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .models import AuditEvent, CompanyContext
from .prompt_config_ports import ControlPlanePromptConfigStore
from .store_utils import now_utc, to_db_value
from .tables import AgentPromptConfigTable, AgentRoleTable, AuditEventTable, CompanyContextTable


class SqlAlchemyControlPlanePromptConfigStore(ControlPlanePromptConfigStore):
    """Session-scoped prompt-configuration store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._agents = SqlAlchemyControlPlaneAgentRegistryStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await self._companies.get_company(company_id)

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentRoleTable | None:
        return await self._agents.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def get_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentPromptConfigTable | None:
        result = await self._session.execute(
            select(AgentPromptConfigTable).where(
                AgentPromptConfigTable.company_id == company_id,
                AgentPromptConfigTable.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPromptConfigTable:
        row = await self.get_agent_prompt_config(
            company_id=company_id,
            agent_id=agent_id,
        )
        if row is None:
            row = AgentPromptConfigTable(
                company_id=company_id,
                agent_id=agent_id,
                system_prompt=system_prompt,
                updated_by=updated_by,
                metadata_json=to_db_value(metadata or {}),
            )
            self._session.add(row)
        else:
            row.system_prompt = system_prompt
            row.updated_by = updated_by
            if metadata is not None:
                row.metadata_json = to_db_value(metadata)
            row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await self._audits.append_audit_event(event)
