"""PJM outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.pjm_agent.core.decomposition_orchestrator import DecompositionOrchestrator
from agents.pjm_agent.db.repository import PJMEventOutboxRepository
from agents.pjm_agent.models import PJMEventOutbox
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


def _outbox_store():
    store = MagicMock()
    store.add = AsyncMock()
    store.stage = AsyncMock()
    store.list_pending = AsyncMock(return_value=[])
    store.mark_published = AsyncMock()
    store.mark_failed = AsyncMock()
    return store


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_pjm_01",
        "event_type": EventTypes.PM_DECOMPOSE_COMPLETED,
        "source_agent": "pjm-agent",
        "payload": {
            "wp_id": 123,
            "status": "approved",
            "user_story_count": 1,
            "task_count": 1,
        },
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=PJMEventOutbox, **defaults)


@pytest.mark.asyncio
async def test_pjm_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = PJMEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.PM_DECOMPOSE_COMPLETED,
        source_agent="pjm-agent",
        payload={
            "wp_id": 123,
            "status": "approved",
            "user_story_count": 1,
            "task_count": 1,
        },
        trace_id="trace-pjm",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.PM_DECOMPOSE_COMPLETED
    assert row.source_agent == "pjm-agent"
    assert row.payload["wp_id"] == 123
    assert row.trace_id == "trace-pjm"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_pending_pjm_events_marks_success():
    db = _db_manager_with_session()
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    orchestrator = DecompositionOrchestrator(
        db_manager=db,
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=bus,
        outbox_store=_outbox_store(),
    )
    orchestrator._mark_pjm_event_published = AsyncMock()
    orchestrator._mark_pjm_event_failed = AsyncMock()

    row = _outbox_row()
    outbox_store = _outbox_store()
    outbox_store.list_pending = AsyncMock(return_value=[row])
    orchestrator._outbox_store = outbox_store

    result = await orchestrator.publish_pending_pjm_events(limit=5)

    outbox_store.list_pending.assert_awaited_once_with(limit=5)
    bus.publish.assert_awaited_once()
    event = bus.publish.await_args.args[0]
    assert event.event_id == "evt_pjm_01"
    assert event.event_type == EventTypes.PM_DECOMPOSE_COMPLETED
    assert event.payload["wp_id"] == 123
    orchestrator._mark_pjm_event_published.assert_awaited_once_with(event)
    orchestrator._mark_pjm_event_failed.assert_not_awaited()
    assert result == {"total": 1, "published": 1, "failed": 0}


@pytest.mark.asyncio
async def test_publish_pending_pjm_events_marks_failure_and_continues():
    db = _db_manager_with_session()
    bus = MagicMock()
    bus.publish = AsyncMock(side_effect=[RuntimeError("broker down"), True])
    orchestrator = DecompositionOrchestrator(
        db_manager=db,
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=bus,
        outbox_store=_outbox_store(),
    )
    orchestrator._mark_pjm_event_published = AsyncMock()
    orchestrator._mark_pjm_event_failed = AsyncMock()

    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store = _outbox_store()
    outbox_store.list_pending = AsyncMock(return_value=[failed_row, ok_row])
    orchestrator._outbox_store = outbox_store

    result = await orchestrator.publish_pending_pjm_events(limit=2)

    assert bus.publish.await_count == 2
    orchestrator._mark_pjm_event_failed.assert_awaited_once()
    orchestrator._mark_pjm_event_published.assert_awaited_once()
    assert result == {"total": 2, "published": 1, "failed": 1}


@pytest.mark.asyncio
async def test_publish_event_via_outbox_stages_before_publish():
    db = _db_manager_with_session()
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    orchestrator = DecompositionOrchestrator(
        db_manager=db,
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=bus,
        outbox_store=_outbox_store(),
    )
    orchestrator._mark_pjm_event_published = AsyncMock()
    orchestrator._mark_pjm_event_failed = AsyncMock()

    outbox = _outbox_store()
    event = Event.create(
        event_type=EventTypes.PM_APPROVAL_TIMEOUT,
        source_agent="pjm-agent",
        payload={"record_id": "dec_001", "age_hours": 25.0},
    )

    orchestrator._outbox_store = outbox

    await orchestrator.publish_event_via_outbox(event, wp_id=123)

    outbox.add.assert_awaited_once_with(event)
    bus.publish.assert_awaited_once_with(event)
    orchestrator._mark_pjm_event_published.assert_awaited_once_with(event)
    orchestrator._mark_pjm_event_failed.assert_not_awaited()
