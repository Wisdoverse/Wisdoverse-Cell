"""Tests for Analysis report delivery application use cases."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.report_delivery_use_cases import (
    AnalysisReportDeliveryUseCase,
)
from shared.schemas.event import Event, EventTypes


class _Factory:
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="analysis-module",
            payload=payload,
            trace_id=trace_id,
        )


class _Metrics:
    def __init__(self) -> None:
        self.reports: list[str] = []

    def record_report(self, report_type: str) -> None:
        self.reports.append(report_type)


def _use_case():
    daily = AsyncMock()
    daily.generate = AsyncMock(
        return_value={"content": "daily content", "summary": "daily summary"}
    )
    daily.push_to_chat = AsyncMock(return_value=True)

    weekly = AsyncMock()
    weekly.generate = AsyncMock(
        return_value={"content": "weekly content", "summary": "weekly summary"}
    )
    weekly.push_to_chat = AsyncMock(return_value=True)

    metrics = _Metrics()
    return (
        AnalysisReportDeliveryUseCase(
            daily=daily,
            weekly=weekly,
            event_factory=_Factory(),
            metrics=metrics,
        ),
        daily,
        weekly,
        metrics,
    )


@pytest.mark.asyncio
async def test_deliver_daily_generates_pushes_and_returns_event() -> None:
    use_case, daily, weekly, metrics = _use_case()

    event = await use_case.deliver_daily(trace_id="trace-analysis")

    assert event.event_type == EventTypes.REPORT_DAILY_GENERATED
    assert event.payload["summary"] == "daily summary"
    assert event.payload["date"]
    assert event.metadata.trace_id == "trace-analysis"
    assert metrics.reports == ["daily"]
    daily.generate.assert_awaited_once_with()
    daily.push_to_chat.assert_awaited_once_with("daily content")
    weekly.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_weekly_generates_pushes_and_returns_event() -> None:
    use_case, daily, weekly, metrics = _use_case()

    event = await use_case.deliver_weekly(trace_id="trace-analysis")

    assert event.event_type == EventTypes.REPORT_WEEKLY_GENERATED
    assert event.payload == {"summary": "weekly summary"}
    assert event.metadata.trace_id == "trace-analysis"
    assert metrics.reports == ["weekly"]
    weekly.generate.assert_awaited_once_with()
    weekly.push_to_chat.assert_awaited_once_with("weekly content")
    daily.generate.assert_not_awaited()
