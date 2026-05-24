"""SQLAlchemy adapter for control-plane agent prompt configuration."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import AgentRoleId, CompanyId

from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .domain_records import agent_prompt_config_record
from .models import AgentPromptConfig, AgentRole, AuditEvent, CompanyContext
from .prompt_config_ports import ControlPlanePromptConfigStore
from .store_utils import now_utc, to_db_value
from .tables import AgentPromptConfigTable


class SqlAlchemyControlPlanePromptConfigStore(ControlPlanePromptConfigStore):
    """Session-scoped prompt-configuration store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._agents = SqlAlchemyControlPlaneAgentRegistryStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        return await self._companies.get_company(company_id)

    async def get_agent_role(
        self,
        *,
        company_id: CompanyId,
        agent_id: AgentRoleId,
    ) -> AgentRole | None:
        return await self._agents.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def get_agent_prompt_config(
        self,
        *,
        company_id: CompanyId,
        agent_id: AgentRoleId,
    ) -> AgentPromptConfig | None:
        row = await self._get_agent_prompt_config_row(
            company_id=company_id,
            agent_id=agent_id,
        )
        return agent_prompt_config_record(row) if row is not None else None

    async def _get_agent_prompt_config_row(
        self,
        *,
        company_id: CompanyId,
        agent_id: AgentRoleId,
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
        company_id: CompanyId,
        agent_id: AgentRoleId,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPromptConfig:
        row = await self._get_agent_prompt_config_row(
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
        return agent_prompt_config_record(row)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._audits.append_audit_event(event)
