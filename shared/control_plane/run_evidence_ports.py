"""Ports for control-plane run evidence artifact creation."""
from __future__ import annotations

from typing import Protocol

from .models import ApprovalRequest, Artifact, AuditEvent, BudgetUsage


class ControlPlaneRunEvidenceStore(Protocol):
    """Persistence operations required to build run evidence artifacts."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """Return approvals linked to one run."""

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsage]:
        """Return budget usage linked to one run."""

    async def list_audit_events(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Return audit events linked to one run."""

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        """Create an artifact."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append an audit event."""
