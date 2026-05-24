"""Ports for control-plane agent prompt configuration."""

from __future__ import annotations

from typing import Any, Protocol

from shared.core.identifiers import AgentRoleId, CompanyId

from .models import AgentPromptConfig, AgentRole, AuditEvent, CompanyContext


class ControlPlanePromptConfigStore(Protocol):
    """Read-side persistence required by prompt-configuration helpers."""

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def get_agent_role(
        self,
        *,
        company_id: CompanyId,
        agent_id: AgentRoleId,
    ) -> AgentRole | None:
        """Return an agent role if the target exists."""

    async def get_agent_prompt_config(
        self,
        *,
        company_id: CompanyId,
        agent_id: AgentRoleId,
    ) -> AgentPromptConfig | None:
        """Return a stored prompt configuration if present."""

    async def upsert_agent_prompt_config(
        self,
        *,
        company_id: CompanyId,
        agent_id: AgentRoleId,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPromptConfig:
        """Create or update one prompt configuration."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
