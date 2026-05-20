"""SQLAlchemy adapter for control-plane evolution proposal persistence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .evolution_proposal_ports import ControlPlaneEvolutionProposalStore
from .models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    CompanyContext,
    EvolutionProposal,
)
from .store_utils import model_values, now_utc
from .tables import (
    ApprovalRequestTable,
    AuditEventTable,
    CompanyContextTable,
    EvolutionProposalTable,
)


class SqlAlchemyControlPlaneEvolutionProposalStore(
    ControlPlaneEvolutionProposalStore
):
    """Session-scoped evolution proposal store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)
        self._approvals = SqlAlchemyControlPlaneApprovalStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await self._companies.get_company(company_id)

    async def request_approval(self, approval: ApprovalRequest) -> ApprovalRequestTable:
        return await self._approvals.request_approval(approval)

    async def get_approval(self, approval_id: str) -> ApprovalRequestTable | None:
        return await self._approvals.get_approval(approval_id)

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequestTable | None:
        return await self._approvals.resolve_approval(
            approval_id,
            status=status,
            resolved_by=resolved_by,
        )

    async def create_evolution_proposal(
        self, proposal: EvolutionProposal
    ) -> EvolutionProposalTable:
        row = EvolutionProposalTable(**model_values(proposal))
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_evolution_proposal(
        self, proposal_id: str
    ) -> EvolutionProposalTable | None:
        result = await self._session.execute(
            select(EvolutionProposalTable).where(
                EvolutionProposalTable.proposal_id == proposal_id
            )
        )
        return result.scalar_one_or_none()

    async def list_evolution_proposals(
        self,
        *,
        company_id: str,
        tier: str | None = None,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionProposalTable]:
        query = select(EvolutionProposalTable).where(
            EvolutionProposalTable.company_id == company_id
        )
        if tier:
            query = query.where(EvolutionProposalTable.tier == tier)
        if approval_state:
            query = query.where(EvolutionProposalTable.approval_state == approval_state)
        if rollout_state:
            query = query.where(EvolutionProposalTable.rollout_state == rollout_state)
        if scope:
            query = query.where(EvolutionProposalTable.scope.ilike(f"%{scope}%"))
        result = await self._session.execute(
            query.order_by(EvolutionProposalTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_evolution_proposal_status(
        self,
        proposal_id: str,
        *,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        approval_id: str | None = None,
    ) -> EvolutionProposalTable | None:
        row = await self.get_evolution_proposal(proposal_id)
        if row is None:
            return None
        if approval_state is not None:
            row.approval_state = approval_state
        if rollout_state is not None:
            row.rollout_state = rollout_state
        if approval_id is not None:
            row.approval_id = approval_id
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def update_evolution_proposal_approval_state_by_approval(
        self,
        approval_id: str,
        *,
        approval_state: str,
        rollout_state: str | None = None,
    ) -> EvolutionProposalTable | None:
        result = await self._session.execute(
            select(EvolutionProposalTable).where(
                EvolutionProposalTable.approval_id == approval_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.approval_state = approval_state
        if rollout_state is not None:
            row.rollout_state = rollout_state
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await self._audits.append_audit_event(event)
