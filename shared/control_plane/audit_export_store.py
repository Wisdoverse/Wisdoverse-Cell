"""Read-only SQLAlchemy page adapter for sanitized audit exports."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain_records import audit_event_record
from .models import AuditEvent
from .tables import AuditEventTable


class AuditExportCursorError(ValueError):
    """The cursor is unknown, belongs to another company, or is outside the window."""


class SqlAlchemyAuditExportStore:
    """Session-scoped, select-only audit page store."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_page(
        self,
        *,
        company_id: str,
        since: datetime,
        until: datetime,
        after_id: str | None = None,
        limit: int = 500,
    ) -> list[AuditEvent]:
        """List one ascending keyset page for a single company."""
        if not 1 <= limit <= 500:
            raise ValueError("audit_export_limit_out_of_range")
        query = select(AuditEventTable).where(
            AuditEventTable.company_id == company_id,
            AuditEventTable.created_at >= since,
            AuditEventTable.created_at <= until,
        )
        if after_id:
            cursor_result = await self._session.execute(
                select(AuditEventTable).where(
                    AuditEventTable.company_id == company_id,
                    AuditEventTable.audit_event_id == after_id,
                )
            )
            cursor = cursor_result.scalar_one_or_none()
            if cursor is None:
                raise AuditExportCursorError("audit_export_cursor_invalid")
            cursor_time = _utc(cursor.created_at)
            if cursor_time < _utc(since) or cursor_time > _utc(until):
                raise AuditExportCursorError("audit_export_cursor_outside_window")
            query = query.where(
                or_(
                    AuditEventTable.created_at > cursor.created_at,
                    (AuditEventTable.created_at == cursor.created_at)
                    & (AuditEventTable.audit_event_id > cursor.audit_event_id),
                )
            )
        result = await self._session.execute(
            query.order_by(
                AuditEventTable.created_at.asc(),
                AuditEventTable.audit_event_id.asc(),
            ).limit(limit)
        )
        return [audit_event_record(row) for row in result.scalars().all()]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["AuditExportCursorError", "SqlAlchemyAuditExportStore"]
