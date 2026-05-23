"""Ports for control-plane approval persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import ApprovalRequestId

from .models import ApprovalRequest, ApprovalStatus, AuditEvent, EvolutionProposal


class ControlPlaneApprovalStore(Protocol):
    """Persistence operations required by approval-gate use cases.

    `approval_id` parameters use the `ApprovalRequestId` `NewType` from
    `shared.core.identifiers` (DDD-007 adoption).
    """

    async def request_approval(
        self,
        approval: ApprovalRequest,
    ) -> ApprovalRequest:
        """Persist a new approval request."""

    async def get_approval(self, approval_id: ApprovalRequestId) -> ApprovalRequest | None:
        """Return one approval request by typed identifier."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """Return approval requests for one company."""

    async def resolve_approval(
        self,
        approval_id: ApprovalRequestId,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequest | None:
        """Resolve an approval request by typed identifier."""

    async def update_evolution_proposal_approval_state_by_approval(
        self,
        approval_id: ApprovalRequestId,
        *,
        approval_state: str,
        rollout_state: str | None = None,
    ) -> EvolutionProposal | None:
        """Synchronize an evolution proposal tied to an approval by typed identifier."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
