"""Application use cases for Analysis event orchestration."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from .report_delivery_use_cases import (
    AnalysisReportDeliveryUseCase,
    AnalysisReportGeneratorPort,
)

logger = get_logger("analysis_module.event_use_cases")

CHINA_TZ = ZoneInfo("Asia/Shanghai")


class AnalysisMilestoneCheckerPort(Protocol):
    async def check(self) -> list[dict[str, Any]]:
        """Return milestone risks."""

    async def push_risks(self, risks: list[dict[str, Any]]) -> bool:
        """Push milestone risk notifications."""


class AnalysisQualityEvaluatorPort(Protocol):
    async def evaluate_all(self) -> list[dict[str, Any]]:
        """Evaluate deliverable quality."""


class AnalysisEventFactoryPort(Protocol):
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        """Create an event emitted by the Analysis capability."""


class AnalysisMetricsPort(Protocol):
    def record_report(self, report_type: str) -> None:
        """Record a generated report."""

    def record_risk(self, risk_level: str) -> None:
        """Record one detected risk."""


class NoopAnalysisMetrics:
    def record_report(self, report_type: str) -> None:
        pass

    def record_risk(self, risk_level: str) -> None:
        pass


class ProjectionRefreshPort(Protocol):
    async def refresh_all(
        self, *, project_id: int | None = None
    ) -> dict[str, int]:
        """Refresh projection rows from upstream sources."""


class AnalysisEventUseCase:
    """Handle Analysis subscribed events outside the service shell."""

    def __init__(
        self,
        *,
        daily: AnalysisReportGeneratorPort,
        weekly: AnalysisReportGeneratorPort,
        milestone: AnalysisMilestoneCheckerPort,
        quality: AnalysisQualityEvaluatorPort,
        event_factory: AnalysisEventFactoryPort,
        metrics: AnalysisMetricsPort | None = None,
        now_china: Callable[[], datetime] | None = None,
        projection_updater: ProjectionRefreshPort | None = None,
    ) -> None:
        self._daily = daily
        self._weekly = weekly
        self._milestone = milestone
        self._quality = quality
        self._event_factory = event_factory
        self._metrics = metrics or NoopAnalysisMetrics()
        self._now_china = now_china or (lambda: datetime.now(CHINA_TZ))
        self._projection_updater = projection_updater
        self._report_delivery = AnalysisReportDeliveryUseCase(
            daily=daily,
            weekly=weekly,
            event_factory=event_factory,
            metrics=self._metrics,
        )

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type != EventTypes.SYNC_COMPLETED:
            return []
        return await self._on_sync_completed(event)

    async def _on_sync_completed(self, event: Event) -> list[Event]:
        events: list[Event] = []
        trace_id = event.metadata.trace_id if event.metadata else None

        if self._projection_updater is not None:
            try:
                await self._projection_updater.refresh_all()
            except Exception as exc:
                logger.error("projection_refresh_failed", error=str(exc))

        try:
            events.append(
                await self._report_delivery.deliver_daily(trace_id=trace_id)
            )
        except Exception as exc:
            logger.error("daily_report_failed", error=str(exc))

        try:
            risks = await self._milestone.check()
            if risks:
                await self._milestone.push_risks(risks)
                for risk in risks:
                    self._metrics.record_risk(
                        risk.get("risk_level") or risk.get("severity", "unknown")
                    )
                events.append(
                    self._event_factory.create_event(
                        EventTypes.ANALYSIS_RISK_DETECTED,
                        {"risks": risks},
                        trace_id=trace_id,
                    )
                )
        except Exception as exc:
            logger.error("milestone_check_failed", error=str(exc))

        try:
            results = await self._quality.evaluate_all()
            if results:
                events.append(
                    self._event_factory.create_event(
                        EventTypes.ANALYSIS_QUALITY_EVALUATED,
                        {"evaluations": results},
                        trace_id=trace_id,
                    )
                )
        except Exception as exc:
            logger.error("quality_eval_failed", error=str(exc))

        if self._now_china().weekday() == 4:
            try:
                events.append(
                    await self._report_delivery.deliver_weekly(trace_id=trace_id)
                )
            except Exception as exc:
                logger.error("weekly_report_failed", error=str(exc))

        return events
