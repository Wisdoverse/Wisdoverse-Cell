"""Sync outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.sync.core.sync_ports import SyncEventOutboxStore
from shared.capabilities.sync.db.repository import SyncEventOutboxRepository
from shared.capabilities.sync.models import SyncEventOutbox
from shared.capabilities.sync.service.agent import SyncModule
from shared.schemas.event import Event, EventTypes


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_sync_01",
        "event_type": EventTypes.SYNC_COMPLETED,
        "source_agent": "sync-module",
        "payload": {"scope": "openproject", "synced_count": 1, "errors": []},
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=SyncEventOutbox, **defaults)


class FakeSyncEventOutboxStore(SyncEventOutboxStore):
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added: list[Event] = []
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.last_limit: int | None = None

    async def add(self, event: Event) -> None:
        self.added.append(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


@pytest.mark.asyncio
async def test_sync_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = SyncEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.SYNC_COMPLETED,
        source_agent="sync-module",
        payload={"scope": "openproject", "synced_count": 1, "errors": []},
        trace_id="trace-sync",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.SYNC_COMPLETED
    assert row.source_agent == "sync-module"
    assert row.payload["scope"] == "openproject"
    assert row.trace_id == "trace-sync"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_pending_sync_events_marks_success():
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeSyncEventOutboxStore(rows=[_outbox_row()])
    agent = SyncModule(
        db=AsyncMock(),
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )
    agent._mark_sync_event_published = AsyncMock()
    agent._mark_sync_event_failed = AsyncMock()

    result = await agent.publish_pending_sync_events(limit=5)

    assert outbox_store.last_limit == 5
    publisher.publish.assert_awaited_once()
    bus.publish.assert_not_awaited()
    event = publisher.publish.await_args.args[0]
    assert event.event_id == "evt_sync_01"
    assert event.event_type == EventTypes.SYNC_COMPLETED
    assert event.payload["scope"] == "openproject"
    agent._mark_sync_event_published.assert_awaited_once_with(event)
    agent._mark_sync_event_failed.assert_not_awaited()
    assert result == {"total": 1, "published": 1, "failed": 0}


@pytest.mark.asyncio
async def test_publish_pending_sync_events_marks_failure_and_continues():
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=[RuntimeError("broker down"), True])

    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store = FakeSyncEventOutboxStore(rows=[failed_row, ok_row])
    agent = SyncModule(
        db=AsyncMock(),
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )
    agent._mark_sync_event_published = AsyncMock()
    agent._mark_sync_event_failed = AsyncMock()

    result = await agent.publish_pending_sync_events(limit=2)

    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    agent._mark_sync_event_failed.assert_awaited_once()
    agent._mark_sync_event_published.assert_awaited_once()
    assert result == {"total": 2, "published": 1, "failed": 1}


@pytest.mark.asyncio
async def test_sync_lifecycle_event_is_staged_before_publish():
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeSyncEventOutboxStore()
    agent = SyncModule(
        db=AsyncMock(),
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )
    agent._mark_sync_event_published = AsyncMock()
    agent._mark_sync_event_failed = AsyncMock()

    event = Event.create(
        event_type=EventTypes.SYNC_STARTED,
        source_agent="sync-module",
        payload={"scope": "openproject", "triggered_by": "test"},
    )

    await agent._publish_sync_event_via_outbox(event)

    assert outbox_store.added == [event]
    publisher.publish.assert_awaited_once_with(event)
    bus.publish.assert_not_awaited()
    agent._mark_sync_event_published.assert_awaited_once_with(event)
    agent._mark_sync_event_failed.assert_not_awaited()
