"""Ports for control-plane agent execution operations."""
from __future__ import annotations

from typing import Any, Protocol

from .models import (
    AgentRole,
    AgentRun,
    ApprovalRequest,
    Artifact,
    AuditEvent,
    BudgetUsage,
    CompanyContext,
)


class ControlPlaneAgentOperationStore(Protocol):
    """Persistence operations required by agent wakeup and scheduling."""

    async def get_company(self, company_id: str) -> CompanyContext | None:
        """Return one company context."""

    async def get_agent_role(
        self, *, company_id: str, agent_id: str
    ) -> AgentRole | None:
        """Return one agent role."""

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AgentRole]:
        """Return agent roles for one company."""

    async def create_agent_run(self, run: AgentRun) -> AgentRun:
        """Create an agent run."""

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        """Return one agent run."""

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        """Return agent runs for one company."""

    async def update_agent_run_status(
        self,
        run_id: str,
        status: Any,
        **values: Any,
    ) -> AgentRun | None:
        """Update an agent run status."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """Return approvals for a run."""

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsage]:
        """Return budget usage for a run."""

    async def list_audit_events(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Return audit events for a run."""

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        """Create an artifact."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append an audit event."""
