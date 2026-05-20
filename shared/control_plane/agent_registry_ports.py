"""Ports for control-plane agent registry persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AgentRole, AuditEvent, CompanyContext


class ControlPlaneAgentRegistryStore(Protocol):
    """Persistence operations required by agent registry use cases."""

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def create_agent_role(self, role: AgentRole) -> AgentRole:
        """Create a new agent role definition."""

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentRole | None:
        """Return one agent role definition."""

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
    ) -> list[AgentRole]:
        """Return agent role definitions for one company."""

    async def update_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
        values: dict[str, Any],
    ) -> AgentRole | None:
        """Update one agent role definition."""

    async def update_agent_role_status(
        self,
        *,
        company_id: str,
        agent_id: str,
        status: str,
    ) -> AgentRole | None:
        """Update one agent role status."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
