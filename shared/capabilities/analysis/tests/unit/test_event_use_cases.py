from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.analysis.core.event_use_cases import AnalysisEventUseCase
from shared.schemas.event import Event, EventTypes


def _sync_completed_event(trace_id: str = "trace-analysis") -> Event:
    return Event.create(
        event_type=EventTypes.SYNC_COMPLETED,
        source_agent="sync-module",
        payload={"synced": 10},
        trace_id=trace_id,
    )


def _event_factory():
    factory = MagicMock()
    factory.create_event.side_effect = lambda event_type, payload, trace_id=None: (
        Event.create(
            event_type=event_type,
            source_agent="analysis-module",
            payload=payload,
            trace_id=trace_id,
        )
    )
    return factory


def _use_case(
    *,
    daily: AsyncMock | None = None,
    weekly: AsyncMock | None = None,
    milestone: AsyncMock | None = None,
    quality: AsyncMock | None = None,
    metrics: MagicMock | None = None,
    now_china=None,
) -> AnalysisEventUseCase:
    if daily is None:
        daily = AsyncMock()
        daily.generate = AsyncMock(return_value={"content": "daily", "summary": "done"})
        daily.push_to_chat = AsyncMock(return_value=True)
    if weekly is None:
        weekly = AsyncMock()
        weekly.generate = AsyncMock(return_value={"content": "weekly", "summary": "week"})
        weekly.push_to_chat = AsyncMock(return_value=True)
    if milestone is None:
        milestone = AsyncMock()
        milestone.check = AsyncMock(return_value=[])
        milestone.push_risks = AsyncMock(return_value=True)
    if quality is None:
        quality = AsyncMock()
        quality.evaluate_all = AsyncMock(return_value=[])
    if metrics is None:
        metrics = MagicMock()

    return AnalysisEventUseCase(
        daily=daily,
        weekly=weekly,
        milestone=milestone,
        quality=quality,
        event_factory=_event_factory(),
        metrics=metrics,
        now_china=now_china or (lambda: datetime(2026, 5, 18)),
    )


@pytest.mark.asyncio
async def test_sync_completed_generates_daily_risk_and_quality_events() -> None:
    milestone = AsyncMock()
    milestone.check = AsyncMock(
        return_value=[{"risk_level": "critical", "message": "blocked"}]
    )
    milestone.push_risks = AsyncMock(return_value=True)
    quality = AsyncMock()
    quality.evaluate_all = AsyncMock(return_value=[{"task": "T1", "quality": "ok"}])
    metrics = MagicMock()

    result = await _use_case(
        milestone=milestone,
        quality=quality,
        metrics=metrics,
    ).handle(_sync_completed_event())

    event_types = [event.event_type for event in result]
    assert EventTypes.REPORT_DAILY_GENERATED in event_types
    assert EventTypes.ANALYSIS_RISK_DETECTED in event_types
    assert EventTypes.ANALYSIS_QUALITY_EVALUATED in event_types
    assert all(event.metadata.trace_id == "trace-analysis" for event in result)
    milestone.push_risks.assert_awaited_once()
    metrics.record_report.assert_called_once_with("daily")
    metrics.record_risk.assert_called_once_with("critical")


@pytest.mark.asyncio
async def test_daily_failure_does_not_block_risk_checks() -> None:
    daily = AsyncMock()
    daily.generate = AsyncMock(side_effect=RuntimeError("bitable error"))
    daily.push_to_chat = AsyncMock()
    milestone = AsyncMock()
    milestone.check = AsyncMock(
        return_value=[{"risk_level": "warning", "message": "slow"}]
    )
    milestone.push_risks = AsyncMock(return_value=True)

    result = await _use_case(daily=daily, milestone=milestone).handle(
        _sync_completed_event()
    )

    event_types = [event.event_type for event in result]
    assert EventTypes.REPORT_DAILY_GENERATED not in event_types
    assert EventTypes.ANALYSIS_RISK_DETECTED in event_types
    milestone.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_risks_or_quality_results_emit_only_daily_event() -> None:
    result = await _use_case().handle(_sync_completed_event())

    event_types = [event.event_type for event in result]
    assert event_types == [EventTypes.REPORT_DAILY_GENERATED]


@pytest.mark.asyncio
async def test_weekly_report_is_generated_on_friday() -> None:
    result = await _use_case(
        now_china=lambda: datetime(2026, 5, 22),
    ).handle(_sync_completed_event())

    event_types = [event.event_type for event in result]
    assert EventTypes.REPORT_WEEKLY_GENERATED in event_types


@pytest.mark.asyncio
async def test_unknown_event_is_ignored() -> None:
    event = Event.create(
        event_type="unknown.event",
        source_agent="test",
        payload={},
    )

    result = await _use_case().handle(event)

    assert result == []
