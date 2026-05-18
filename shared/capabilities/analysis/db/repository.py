"""Repository for the analysis module."""
import inspect
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..models.event_outbox import AnalysisEventOutbox
from ..models.report import ReportLog


class ReportLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, report_type: str, report_date: datetime, content: str = "") -> ReportLog:
        log = ReportLog(report_type=report_type, report_date=report_date, content=content)
        self.session.add(log)
        await self.session.flush()
        return log

    async def mark_pushed(self, log_id: int) -> None:
        result = await self.session.execute(select(ReportLog).where(ReportLog.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            log.status = "pushed"
            log.pushed_at = datetime.now(UTC)
            await self.session.flush()

    async def get_latest(self, report_type: str) -> Optional[ReportLog]:
        result = await self.session.execute(
            select(ReportLog)
            .where(ReportLog.report_type == report_type)
            .order_by(ReportLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class AnalysisEventOutboxRepository:
    """Analysis integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> AnalysisEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = AnalysisEventOutbox(
            event_id=event.event_id,
            event_type=event.event_type,
            source_agent=event.source_agent,
            payload=payload["payload"],
            schema_version=event.schema_version,
            trace_id=payload["metadata"].get("trace_id"),
            correlation_id=payload["metadata"].get("correlation_id"),
            retry_count=payload["metadata"].get("retry_count", 0),
            status="pending",
            attempts=0,
        )
        add_result = self.session.add(row)
        if inspect.isawaitable(add_result):
            await add_result
        flush_result = self.session.flush()
        if inspect.isawaitable(flush_result):
            await flush_result
        return row

    async def list_pending(self, limit: int = 100) -> list[AnalysisEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(AnalysisEventOutbox)
            .where(AnalysisEventOutbox.status == "pending")
            .order_by(
                AnalysisEventOutbox.created_at,
                AnalysisEventOutbox.event_id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(AnalysisEventOutbox)
            .where(AnalysisEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=AnalysisEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(AnalysisEventOutbox)
            .where(AnalysisEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=AnalysisEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )
