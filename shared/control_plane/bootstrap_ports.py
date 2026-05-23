"""Ports for control-plane role bootstrap persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId

from .models import AgentRole, AuditEvent, CompanyContext


class ControlPlaneRoleBootstrapStore(Protocol):
    """Persistence operations required by role bootstrap use cases."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def create_company_if_absent(
        self, company: CompanyContext
    ) -> CompanyContext | None:
        """Create a company context, returning None when it already exists."""

    async def get_agent_role(
        self,
        *,
        company_id: CompanyId,
        agent_id: str,
    ) -> AgentRole | None:
        """Return one agent role if it exists."""

    async def create_agent_role_if_absent(self, role: AgentRole) -> AgentRole | None:
        """Create one agent role, returning None when it already exists."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
