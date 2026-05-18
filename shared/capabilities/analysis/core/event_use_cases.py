"""Application use cases for Analysis event orchestration."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

logger = get_logger("analysis_module.event_use_cases")

CHINA_TZ = ZoneInfo("Asia/Shanghai")


class AnalysisReportGeneratorPort(Protocol):
    async def generate(self) -> dict[str, Any]:
        """Generate an analysis report."""

    async def push_to_chat(self, content: str) -> bool:
        """Push report content to chat."""


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
    ) -> None:
        self._daily = daily
        self._weekly = weekly
        self._milestone = milestone
        self._quality = quality
        self._event_factory = event_factory
        self._metrics = metrics or NoopAnalysisMetrics()
        self._now_china = now_china or (lambda: datetime.now(CHINA_TZ))

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type != EventTypes.SYNC_COMPLETED:
            return []
        return await self._on_sync_completed(event)

    async def _on_sync_completed(self, event: Event) -> list[Event]:
        events: list[Event] = []
        trace_id = event.metadata.trace_id if event.metadata else None

        try:
            report = await self._daily.generate()
            await self._daily.push_to_chat(report["content"])
            self._metrics.record_report("daily")
            events.append(
                self._event_factory.create_event(
                    EventTypes.REPORT_DAILY_GENERATED,
                    {
                        "date": datetime.now(UTC).isoformat(),
                        "summary": report["summary"],
                    },
                    trace_id=trace_id,
                )
            )
        except Exception as exc:
            logger.error("daily_report_failed", error=str(exc))

        try:
            risks = await self._milestone.check()
            if risks:
                await self._milestone.push_risks(risks)
                for risk in risks:
                    self._metrics.record_risk(risk.get("risk_level", "unknown"))
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
                report = await self._weekly.generate()
                await self._weekly.push_to_chat(report["content"])
                events.append(
                    self._event_factory.create_event(
                        EventTypes.REPORT_WEEKLY_GENERATED,
                        {"summary": report["summary"]},
                        trace_id=trace_id,
                    )
                )
            except Exception as exc:
                logger.error("weekly_report_failed", error=str(exc))

        return events
