"""Tests for the Analysis application facade."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.application_facade import (
    AnalysisApplicationFacade,
)
from shared.schemas.event import Event, EventTypes


class _EventFactory:
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
        self.risks: list[str] = []

    def record_report(self, report_type: str) -> None:
        self.reports.append(report_type)

    def record_risk(self, risk_level: str) -> None:
        self.risks.append(risk_level)


class _HealthStore:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


class _OutboxRow:
    event_id = "evt_pending"
    event_type = EventTypes.ANALYSIS_RISK_DETECTED
    source_agent = "analysis-module"
    payload = {"risks": [{"severity": "warning"}]}
    schema_version = "1.0"
    trace_id = "trace-analysis"
    correlation_id = None
    retry_count = 0
    created_at = datetime.now(UTC)


class _OutboxStore:
    def __init__(self, rows: list[_OutboxRow] | None = None) -> None:
        self.added: list[Event] = []
        self.rows = rows or []
        self.last_limit: int | None = None
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def add(self, event: Event) -> None:
        self.added.append(event)

    async def list_pending(self, limit: int = 100) -> list[_OutboxRow]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


def _component_set():
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

    milestone = AsyncMock()
    milestone.check = AsyncMock(return_value=[{"risk_level": "warning"}])
    milestone.push_risks = AsyncMock(return_value=True)

    quality = AsyncMock()
    quality.evaluate_all = AsyncMock(return_value=[{"quality": "ok"}])

    return daily, weekly, milestone, quality


def _facade(
    *,
    standard_request_handler=None,
    health_store=None,
    event_bus=None,
    outbox_store=None,
    event_publisher=None,
):
    daily, weekly, milestone, quality = _component_set()
    if standard_request_handler is None:
        standard_request_handler = AsyncMock(return_value=None)
    if health_store is None:
        health_store = _HealthStore(True)
    if event_bus is None:
        event_bus = AsyncMock()
        event_bus.connect = AsyncMock()
    if outbox_store is None:
        outbox_store = _OutboxStore()
    if event_publisher is None:
        event_publisher = AsyncMock()
        event_publisher.publish = AsyncMock(return_value=True)
    return (
        AnalysisApplicationFacade(
            standard_request_handler=standard_request_handler,
            daily_provider=lambda: daily,
            weekly_provider=lambda: weekly,
            milestone_provider=lambda: milestone,
            quality_provider=lambda: quality,
            event_factory=_EventFactory(),
            metrics=_Metrics(),
            health_store_provider=lambda: health_store,
            event_bus=event_bus,
            outbox_store_provider=lambda: outbox_store,
            event_publisher=event_publisher,
        ),
        daily,
        weekly,
        milestone,
        quality,
    )


@pytest.mark.asyncio
async def test_analysis_application_facade_preserves_standard_request_boundary() -> None:
    standard_handler = AsyncMock(return_value={"agent_id": "analysis-module"})
    facade, daily, _, _, _ = _facade(standard_request_handler=standard_handler)

    result = await facade.handle_request({"action": "describe"})

    assert result == {"agent_id": "analysis-module"}
    standard_handler.assert_awaited_once()
    daily.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_application_facade_dispatches_request_use_case() -> None:
    facade, daily, _, _, _ = _facade()

    result = await facade.handle_request({"action": "daily_report"})

    assert result["summary"] == "daily summary"
    daily.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_analysis_application_facade_dispatches_event_use_case() -> None:
    facade, daily, _, milestone, quality = _facade()
    event = Event.create(
        event_type=EventTypes.SYNC_COMPLETED,
        source_agent="sync-module",
        payload={},
        trace_id="trace-analysis",
    )

    events = await facade.handle_event(event)

    event_types = {result_event.event_type for result_event in events}
    assert EventTypes.REPORT_DAILY_GENERATED in event_types
    assert EventTypes.ANALYSIS_RISK_DETECTED in event_types
    assert EventTypes.ANALYSIS_QUALITY_EVALUATED in event_types
    daily.generate.assert_awaited_once()
    milestone.check.assert_awaited_once()
    quality.evaluate_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_analysis_application_facade_delegates_health_check() -> None:
    facade, *_ = _facade(health_store=_HealthStore(True))

    result = await facade.health_check()

    assert result == {"database": True, "event_bus": True}


@pytest.mark.asyncio
async def test_analysis_application_facade_delegates_outbox_delivery() -> None:
    outbox_store = _OutboxStore(rows=[_OutboxRow()])
    event_publisher = AsyncMock()
    event_publisher.publish = AsyncMock(return_value=True)
    facade, *_ = _facade(
        outbox_store=outbox_store,
        event_publisher=event_publisher,
    )
    event = Event.create(
        event_type=EventTypes.REPORT_DAILY_GENERATED,
        source_agent="analysis-module",
        payload={"summary": "ok"},
    )

    ok = await facade.publish_event_via_outbox(event)
    result = await facade.publish_pending_analysis_events(limit=1)

    assert ok is True
    assert outbox_store.added == [event]
    assert outbox_store.last_limit == 1
    assert outbox_store.published == [event.event_id, "evt_pending"]
    assert result == {"total": 1, "published": 1, "failed": 0}
