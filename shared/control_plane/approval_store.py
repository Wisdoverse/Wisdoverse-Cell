"""SQLAlchemy adapter for control-plane approval persistence."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .approval_ports import ControlPlaneApprovalStore
from .models import ApprovalRequest, ApprovalStatus, AuditEvent
from .repository import ControlPlaneRepository
from .tables import ApprovalRequestTable


class SqlAlchemyControlPlaneApprovalStore(ControlPlaneApprovalStore):
    """Session-scoped control-plane approval store."""

    def __init__(self, session: AsyncSession):
        self._approvals = ControlPlaneRepository(session)

    async def request_approval(
        self,
        approval: ApprovalRequest,
    ) -> ApprovalRequestTable:
        return await self._approvals.request_approval(approval)

    async def get_approval(self, approval_id: str) -> ApprovalRequestTable | None:
        return await self._approvals.get_approval(approval_id)

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequestTable]:
        return await self._approvals.list_approvals(
            company_id=company_id,
            status=status,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )

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

    async def update_evolution_proposal_approval_state_by_approval(
        self,
        approval_id: str,
        *,
        approval_state: str,
        rollout_state: str | None = None,
    ):
        return await self._approvals.update_evolution_proposal_approval_state_by_approval(
            approval_id,
            approval_state=approval_state,
            rollout_state=rollout_state,
        )

    async def append_audit_event(self, event: AuditEvent):
        return await self._approvals.append_audit_event(event)
