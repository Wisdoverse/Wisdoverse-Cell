"""Ports for control-plane decision persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AuditEvent, CompanyContext, Decision


class ControlPlaneDecisionStore(Protocol):
    """Persistence operations required by decision use cases."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def get_agent_run(self, run_id: str) -> Any | None:
        """Return one agent run for linkage validation."""

    async def get_goal(self, goal_id: str) -> Any | None:
        """Return one goal for linkage validation."""

    async def get_work_item(self, work_item_id: str) -> Any | None:
        """Return one work item for linkage validation."""

    async def create_decision(self, decision: Decision) -> Any:
        """Create a decision."""

    async def get_decision(self, decision_id: str) -> Any | None:
        """Return one decision."""

    async def list_decisions(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return decisions for one company."""

    async def update_decision_status(
        self,
        decision_id: str,
        *,
        status: str,
        selected_option: str | None = None,
        decided_by: str | None = None,
    ) -> Any | None:
        """Update one decision status."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
