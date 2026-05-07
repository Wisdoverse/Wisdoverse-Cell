"""Repository for the analysis module."""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
