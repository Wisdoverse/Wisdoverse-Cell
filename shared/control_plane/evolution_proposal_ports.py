"""Ports for control-plane evolution proposal persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId

from .models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    CompanyContext,
    EvolutionProposal,
)


class ControlPlaneEvolutionProposalStore(Protocol):
    """Persistence operations required by evolution proposal use cases."""

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def request_approval(self, approval: ApprovalRequest) -> ApprovalRequest:
        """Persist a new approval request."""

    async def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Return one approval request."""

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequest | None:
        """Resolve an approval request."""

    async def create_evolution_proposal(
        self, proposal: EvolutionProposal
    ) -> EvolutionProposal:
        """Create an evolution proposal."""

    async def get_evolution_proposal(
        self, proposal_id: str
    ) -> EvolutionProposal | None:
        """Return one evolution proposal."""

    async def list_evolution_proposals(
        self,
        *,
        company_id: CompanyId,
        tier: str | None = None,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionProposal]:
        """Return evolution proposals for one company."""

    async def update_evolution_proposal_status(
        self,
        proposal_id: str,
        *,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        approval_id: str | None = None,
    ) -> EvolutionProposal | None:
        """Update one evolution proposal status."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
