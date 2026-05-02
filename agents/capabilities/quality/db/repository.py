"""Repository - qa_agent"""

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..models.qa import QAAcceptanceResult, QAAcceptanceRun
from ..models.schemas import QACheckAggregate, QARunStats

logger = get_logger("qa_agent.repository")


class AcceptanceRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> QAAcceptanceRun:
        run = QAAcceptanceRun(**kwargs)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: str) -> Optional[QAAcceptanceRun]:
        result = await self.session.execute(
            select(QAAcceptanceRun).where(QAAcceptanceRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[QAAcceptanceRun]:
        query = select(QAAcceptanceRun).order_by(desc(QAAcceptanceRun.created_at))
        if agent_name:
            query = query.where(QAAcceptanceRun.agent_name == agent_name)

        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        cutoff = datetime.now(UTC) - timedelta(days=days)

        # Basic stats — mutually exclusive buckets:
        #   failed = L0 FAIL (regardless of L1)
        #   warn   = L0 PASS + L1 WARN
        #   passed = L0 PASS + L1 PASS
        _count = func.count(QAAcceptanceRun.id)
        _l0_pass = QAAcceptanceRun.l0_status == "PASS"
        _l0_fail = QAAcceptanceRun.l0_status == "FAIL"
        _l1_warn = QAAcceptanceRun.l1_status == "WARN"
        _l1_pass = QAAcceptanceRun.l1_status == "PASS"
        base_query = select(
            _count.label("total"),
            _count.filter(_l0_pass, _l1_pass).label("passed"),
            _count.filter(_l0_pass, _l1_warn).label("warn"),
            _count.filter(_l0_fail).label("fail"),
            func.avg(QAAcceptanceRun.duration_seconds).label("avg_duration"),
        ).where(QAAcceptanceRun.created_at >= cutoff)

        if agent_name:
            base_query = base_query.where(QAAcceptanceRun.agent_name == agent_name)

        stats_result = await self.session.execute(base_query)
        row = stats_result.one()

        total = row.total or 0
        pass_runs = row.passed or 0
        warn_runs = row.warn or 0
        failed_runs = row.fail or 0
        avg_duration = float(row.avg_duration or 0.0)
        l0_fail_rate = (failed_runs / total) if total > 0 else 0.0

        # Top L0 failures
        l0_query = (
            select(QAAcceptanceResult.check_name, func.count(QAAcceptanceResult.id).label("count"))
            .join(QAAcceptanceRun)
            .where(QAAcceptanceRun.created_at >= cutoff)
            .where(QAAcceptanceResult.level == "L0")
            .where(QAAcceptanceResult.status == "FAIL")
        )
        if agent_name:
            l0_query = l0_query.where(QAAcceptanceRun.agent_name == agent_name)
        l0_query = l0_query.group_by(QAAcceptanceResult.check_name).order_by(desc("count")).limit(5)
        l0_failures = await self.session.execute(l0_query)
        top_l0 = [QACheckAggregate(check=r.check_name, count=r.count) for r in l0_failures.all()]

        # Top L1 warnings
        l1_query = (
            select(QAAcceptanceResult.check_name, func.count(QAAcceptanceResult.id).label("count"))
            .join(QAAcceptanceRun)
            .where(QAAcceptanceRun.created_at >= cutoff)
            .where(QAAcceptanceResult.level == "L1")
            .where(QAAcceptanceResult.status == "WARN")
        )
        if agent_name:
            l1_query = l1_query.where(QAAcceptanceRun.agent_name == agent_name)
        l1_query = l1_query.group_by(QAAcceptanceResult.check_name).order_by(desc("count")).limit(5)
        l1_warnings = await self.session.execute(l1_query)
        top_l1 = [QACheckAggregate(check=r.check_name, count=r.count) for r in l1_warnings.all()]

        return QARunStats(
            agent_name=agent_name,
            days=days,
            total_runs=total,
            pass_runs=pass_runs,
            warn_runs=warn_runs,
            failed_runs=failed_runs,
            l0_fail_rate=l0_fail_rate,
            avg_duration_seconds=avg_duration,
            top_l0_failures=top_l0,
            top_l1_warnings=top_l1,
        )


class AcceptanceResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_batch(self, results: list[dict[str, Any]]) -> list[QAAcceptanceResult]:
        db_results = [QAAcceptanceResult(**r) for r in results]
        self.session.add_all(db_results)
        await self.session.flush()
        return db_results

    async def list_by_run_id(self, run_id: str) -> list[QAAcceptanceResult]:
        result = await self.session.execute(
            select(QAAcceptanceResult)
            .where(QAAcceptanceResult.run_id == run_id)
            .order_by(QAAcceptanceResult.level, QAAcceptanceResult.status)
        )
        return list(result.scalars().all())
