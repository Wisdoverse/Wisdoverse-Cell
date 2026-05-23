"""Ports for control-plane audit and timeline queries."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId

from .models import (
    AgentRun,
    ApprovalRequest,
    Artifact,
    AuditEvent,
    BudgetUsage,
    Decision,
)


class ControlPlaneAuditTimelineStore(Protocol):
    """Persistence operations required by audit and timeline use cases."""

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        """Return one agent run."""

    async def list_agent_runs(
        self,
        *,
        company_id: CompanyId,
        trace_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        """Return agent runs for one company."""

    async def list_audit_events(
        self,
        *,
        company_id: CompanyId,
        trace_id: str | None = None,
        run_id: str | None = None,
        work_item_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Return audit events."""

    async def list_approvals(
        self,
        *,
        company_id: CompanyId,
        run_id: str | None = None,
        trace_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """Return approval requests."""

    async def list_budget_usage(
        self,
        *,
        company_id: CompanyId,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsage]:
        """Return budget usage rows."""

    async def list_decisions(
        self,
        *,
        company_id: CompanyId,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Decision]:
        """Return decisions."""

    async def list_artifacts(
        self,
        *,
        company_id: CompanyId,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Artifact]:
        """Return artifacts."""
