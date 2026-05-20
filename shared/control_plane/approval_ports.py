"""Ports for control-plane approval persistence."""
from __future__ import annotations

from typing import Protocol

from .models import ApprovalRequest, ApprovalStatus, AuditEvent, EvolutionProposal


class ControlPlaneApprovalStore(Protocol):
    """Persistence operations required by approval-gate use cases."""

    async def request_approval(
        self,
        approval: ApprovalRequest,
    ) -> ApprovalRequest:
        """Persist a new approval request."""

    async def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Return one approval request."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """Return approval requests for one company."""

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequest | None:
        """Resolve an approval request."""

    async def update_evolution_proposal_approval_state_by_approval(
        self,
        approval_id: str,
        *,
        approval_state: str,
        rollout_state: str | None = None,
    ) -> EvolutionProposal | None:
        """Synchronize an evolution proposal tied to an approval."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
