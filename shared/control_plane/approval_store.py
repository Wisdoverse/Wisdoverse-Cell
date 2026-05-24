"""SQLAlchemy adapter for control-plane approval persistence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import ApprovalRequestId, CompanyId

from .approval_ports import ControlPlaneApprovalStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .domain_records import approval_request_record
from .models import ApprovalRequest, ApprovalStatus, AuditEvent
from .store_utils import model_values, now_utc
from .tables import ApprovalRequestTable


class SqlAlchemyControlPlaneApprovalStore(ControlPlaneApprovalStore):
    """Session-scoped control-plane approval store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)

    async def request_approval(
        self,
        approval: ApprovalRequest,
    ) -> ApprovalRequest:
        row = ApprovalRequestTable(**model_values(approval))
        self._session.add(row)
        await self._session.flush()
        return approval_request_record(row)

    async def get_approval(self, approval_id: ApprovalRequestId) -> ApprovalRequest | None:
        row = await self._get_approval_row(approval_id)
        return approval_request_record(row) if row is not None else None

    async def _get_approval_row(self, approval_id: ApprovalRequestId) -> ApprovalRequestTable | None:
        result = await self._session.execute(
            select(ApprovalRequestTable).where(
                ApprovalRequestTable.approval_id == approval_id
            )
        )
        return result.scalar_one_or_none()

    async def list_approvals(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        query = select(ApprovalRequestTable).where(
            ApprovalRequestTable.company_id == company_id
        )
        if status:
            query = query.where(ApprovalRequestTable.status == status)
        if run_id:
            query = query.where(ApprovalRequestTable.run_id == run_id)
        if trace_id:
            query = query.where(ApprovalRequestTable.trace_id == trace_id)
        if work_item_id:
            query = query.where(ApprovalRequestTable.work_item_id == work_item_id)
        result = await self._session.execute(
            query.order_by(ApprovalRequestTable.created_at.desc()).limit(limit)
        )
        return [approval_request_record(row) for row in result.scalars().all()]

    async def resolve_approval(
        self,
        approval_id: ApprovalRequestId,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequest | None:
        row = await self._get_approval_row(approval_id)
        if row is None:
            return None
        status_value = status.value if isinstance(status, ApprovalStatus) else status
        row.status = status_value
        row.resolved_by = resolved_by
        now = now_utc()
        row.resolved_at = now
        row.updated_at = now
        await self._session.flush()
        return approval_request_record(row)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._companies.append_audit_event(event)
