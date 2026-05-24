"""Application use cases for Analysis report delivery commands."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from shared.schemas.event import Event, EventTypes


class AnalysisReportGeneratorPort(Protocol):
    async def generate(self) -> dict[str, Any]:
        """Generate an analysis report."""

    async def push_to_chat(self, content: str) -> bool:
        """Push report content to chat."""


class AnalysisReportEventFactoryPort(Protocol):
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        """Create an event emitted by the Analysis capability."""


class AnalysisReportMetricsPort(Protocol):
    def record_report(self, report_type: str) -> None:
        """Record a generated report."""


class AnalysisReportDeliveryUseCase:
    """Own the generate -> push -> integration-event boundary for reports."""

    def __init__(
        self,
        *,
        daily: AnalysisReportGeneratorPort,
        weekly: AnalysisReportGeneratorPort,
        event_factory: AnalysisReportEventFactoryPort,
        metrics: AnalysisReportMetricsPort,
    ) -> None:
        self._daily = daily
        self._weekly = weekly
        self._event_factory = event_factory
        self._metrics = metrics

    async def deliver_daily(self, *, trace_id: str | None = None) -> Event:
        """Generate, push, and describe the daily report integration event."""
        report = await self._daily.generate()
        await self._daily.push_to_chat(report["content"])
        self._metrics.record_report("daily")
        return self._event_factory.create_event(
            EventTypes.REPORT_DAILY_GENERATED,
            {
                "date": datetime.now(UTC).isoformat(),
                "summary": report["summary"],
            },
            trace_id=trace_id,
        )

    async def deliver_weekly(self, *, trace_id: str | None = None) -> Event:
        """Generate, push, and describe the weekly report integration event."""
        report = await self._weekly.generate()
        await self._weekly.push_to_chat(report["content"])
        self._metrics.record_report("weekly")
        return self._event_factory.create_event(
            EventTypes.REPORT_WEEKLY_GENERATED,
            {"summary": report["summary"]},
            trace_id=trace_id,
        )


__all__ = [
    "AnalysisReportDeliveryUseCase",
    "AnalysisReportEventFactoryPort",
    "AnalysisReportGeneratorPort",
    "AnalysisReportMetricsPort",
]
