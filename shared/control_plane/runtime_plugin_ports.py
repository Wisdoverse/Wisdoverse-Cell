"""Ports for the control-plane runtime plugin."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AgentRun, AuditEvent, CompanyContext
from .run_evidence_ports import ControlPlaneRunEvidenceStore


class ControlPlaneRuntimePluginStore(ControlPlaneRunEvidenceStore, Protocol):
    """Persistence operations required by runtime plugin use cases."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return one company context."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a company context."""

    async def create_agent_run(self, run: AgentRun) -> Any:
        """Create an agent run."""

    async def update_agent_run_status(
        self,
        run_id: str,
        status: Any,
        **values: Any,
    ) -> Any | None:
        """Update an agent run status."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append an audit event."""

    async def ensure_core_organization_role_agents(
        self,
        *,
        company_id: str,
        company_name: str,
    ) -> list[str]:
        """Ensure durable organization role agents exist."""

    async def ensure_core_runtime_agent_roles(
        self,
        *,
        company_id: str,
        company_name: str,
    ) -> list[str]:
        """Ensure durable frontend-managed runtime agents exist."""
