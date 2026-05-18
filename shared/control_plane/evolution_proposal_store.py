"""SQLAlchemy adapter for control-plane evolution proposal persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .evolution_proposal_ports import ControlPlaneEvolutionProposalStore
from .models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    CompanyContext,
    EvolutionProposal,
)
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneEvolutionProposalStore(
    ControlPlaneEvolutionProposalStore
):
    """Session-scoped evolution proposal store."""

    def __init__(self, session: AsyncSession):
        self._proposals = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._proposals.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._proposals.get_company(company_id)

    async def request_approval(self, approval: ApprovalRequest) -> Any:
        return await self._proposals.request_approval(approval)

    async def get_approval(self, approval_id: str) -> Any | None:
        return await self._proposals.get_approval(approval_id)

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> Any | None:
        return await self._proposals.resolve_approval(
            approval_id,
            status=status,
            resolved_by=resolved_by,
        )

    async def create_evolution_proposal(self, proposal: EvolutionProposal) -> Any:
        return await self._proposals.create_evolution_proposal(proposal)

    async def get_evolution_proposal(self, proposal_id: str) -> Any | None:
        return await self._proposals.get_evolution_proposal(proposal_id)

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
        return await self._proposals.list_evolution_proposals(
            company_id=company_id,
            tier=tier,
            approval_state=approval_state,
            rollout_state=rollout_state,
            scope=scope,
            limit=limit,
        )

    async def update_evolution_proposal_status(
        self,
        proposal_id: str,
        *,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        approval_id: str | None = None,
    ) -> Any | None:
        return await self._proposals.update_evolution_proposal_status(
            proposal_id,
            approval_state=approval_state,
            rollout_state=rollout_state,
            approval_id=approval_id,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._proposals.append_audit_event(event)
