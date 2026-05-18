"""SQLAlchemy adapter for control-plane agent prompt configuration."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent, CompanyContext
from .prompt_config_ports import ControlPlanePromptConfigStore
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlanePromptConfigStore(ControlPlanePromptConfigStore):
    """Session-scoped prompt-configuration store."""

    def __init__(self, session: AsyncSession):
        self._prompts = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._prompts.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._prompts.get_company(company_id)

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        return await self._prompts.get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def get_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        return await self._prompts.get_agent_prompt_config(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def upsert_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        return await self._prompts.upsert_agent_prompt_config(
            company_id=company_id,
            agent_id=agent_id,
            system_prompt=system_prompt,
            updated_by=updated_by,
            metadata=metadata,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._prompts.append_audit_event(event)
