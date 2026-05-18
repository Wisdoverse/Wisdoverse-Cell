"""Ports for control-plane role bootstrap persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AgentRole, AuditEvent, CompanyContext


class ControlPlaneRoleBootstrapStore(Protocol):
    """Persistence operations required by role bootstrap use cases."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def create_company_if_absent(self, company: CompanyContext) -> Any | None:
        """Create a company context, returning None when it already exists."""

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> Any | None:
        """Return one agent role if it exists."""

    async def create_agent_role_if_absent(self, role: AgentRole) -> Any | None:
        """Create one agent role, returning None when it already exists."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
