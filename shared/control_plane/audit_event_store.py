"""SQLAlchemy adapter for control-plane audit event persistence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain_records import audit_event_record
from .models import AuditEvent
from .store_utils import model_values
from .tables import AuditEventTable


class SqlAlchemyControlPlaneAuditEventStore:
    """Session-scoped control-plane audit event store."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        if event.idempotency_key:
            existing = await self._get_audit_by_idempotency(
                event.company_id, event.idempotency_key
            )
            if existing is not None:
                return audit_event_record(existing)

        row = AuditEventTable(**model_values(event))
        self._session.add(row)
        await self._session.flush()
        return audit_event_record(row)

    async def list_audit_events(
        self,
        *,
        company_id: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        work_item_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        query = select(AuditEventTable).where(AuditEventTable.company_id == company_id)
        if trace_id:
            query = query.where(AuditEventTable.trace_id == trace_id)
        if run_id:
            query = query.where(AuditEventTable.run_id == run_id)
        if work_item_id:
            query = query.where(AuditEventTable.work_item_id == work_item_id)
        if target_type:
            query = query.where(AuditEventTable.target_type == target_type)
        if target_id:
            query = query.where(AuditEventTable.target_id == target_id)
        result = await self._session.execute(
            query.order_by(AuditEventTable.created_at.desc()).limit(limit)
        )
        return [audit_event_record(row) for row in result.scalars().all()]

    async def _get_audit_by_idempotency(
        self, company_id: str, idempotency_key: str
    ) -> AuditEventTable | None:
        result = await self._session.execute(
            select(AuditEventTable).where(
                AuditEventTable.company_id == company_id,
                AuditEventTable.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()
