"""Analysis outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.analysis.db.repository import AnalysisEventOutboxRepository
from shared.capabilities.analysis.models import AnalysisEventOutbox
from shared.capabilities.analysis.service.agent import AnalysisModule
from shared.schemas.event import Event, EventTypes


class AsyncSessionContext:
    """Minimal async context manager for mocked db sessions."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _db_manager_with_session():
    db_manager = MagicMock()
    db_manager.session.return_value = AsyncSessionContext(MagicMock())
    return db_manager


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_analysis_01",
        "event_type": EventTypes.ANALYSIS_RISK_DETECTED,
        "source_agent": "analysis-module",
        "payload": {"risks": [{"severity": "warning"}]},
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=AnalysisEventOutbox, **defaults)


class FakeAnalysisOutboxStore:
    def __init__(self):
        self.add = AsyncMock()
        self.list_pending = AsyncMock(return_value=[])
        self.mark_published = AsyncMock()
        self.mark_failed = AsyncMock()


@pytest.mark.asyncio
async def test_analysis_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = AnalysisEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.ANALYSIS_RISK_DETECTED,
        source_agent="analysis-module",
        payload={"risks": [{"severity": "warning"}]},
        trace_id="trace-analysis",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.ANALYSIS_RISK_DETECTED
    assert row.source_agent == "analysis-module"
    assert row.payload["risks"][0]["severity"] == "warning"
    assert row.trace_id == "trace-analysis"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_event_via_outbox_stages_before_publish():
    db = _db_manager_with_session()
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeAnalysisOutboxStore()
    agent = AnalysisModule(
        db=db,
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )

    event = Event.create(
        event_type=EventTypes.REPORT_DAILY_GENERATED,
        source_agent="analysis-module",
        payload={"date": "2026-05-17", "summary": "ok"},
    )

    ok = await agent.publish_event_via_outbox(event)

    assert ok is True
    outbox_store.add.assert_awaited_once_with(event)
    publisher.publish.assert_awaited_once_with(event)
    bus.publish.assert_not_awaited()
    outbox_store.mark_published.assert_awaited_once_with(event.event_id)
    outbox_store.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_pending_analysis_events_marks_failure_and_continues():
    db = _db_manager_with_session()
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=[False, True])
    outbox_store = FakeAnalysisOutboxStore()
    agent = AnalysisModule(
        db=db,
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )

    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store.list_pending = AsyncMock(return_value=[failed_row, ok_row])

    result = await agent.publish_pending_analysis_events(limit=2)

    outbox_store.list_pending.assert_awaited_once_with(limit=2)
    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    outbox_store.mark_failed.assert_awaited_once()
    outbox_store.mark_published.assert_awaited_once_with("evt_ok")
    assert result == {"total": 2, "published": 1, "failed": 1}
