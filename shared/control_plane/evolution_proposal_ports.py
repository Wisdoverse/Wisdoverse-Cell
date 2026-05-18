"""Ports for control-plane evolution proposal persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import ApprovalRequest, ApprovalStatus, AuditEvent, CompanyContext, EvolutionProposal


class ControlPlaneEvolutionProposalStore(Protocol):
    """Persistence operations required by evolution proposal use cases."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def request_approval(self, approval: ApprovalRequest) -> Any:
        """Persist a new approval request."""

    async def get_approval(self, approval_id: str) -> Any | None:
        """Return one approval request."""

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> Any | None:
        """Resolve an approval request."""

    async def create_evolution_proposal(self, proposal: EvolutionProposal) -> Any:
        """Create an evolution proposal."""

    async def get_evolution_proposal(self, proposal_id: str) -> Any | None:
        """Return one evolution proposal."""

    async def list_evolution_proposals(
        self,
        *,
        company_id: str,
        tier: str | None = None,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Return evolution proposals for one company."""

    async def update_evolution_proposal_status(
        self,
        proposal_id: str,
        *,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        approval_id: str | None = None,
    ) -> Any | None:
        """Update one evolution proposal status."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
