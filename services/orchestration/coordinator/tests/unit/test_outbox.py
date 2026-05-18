"""Coordinator outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.orchestration.coordinator.core.outbox_ports import CoordinatorEventOutboxStore
from services.orchestration.coordinator.db.event_outbox import CoordinatorEventOutbox
from services.orchestration.coordinator.db.repository import CoordinatorEventOutboxRepository
from services.orchestration.coordinator.service.agent import CoordinatorAgent
from shared.schemas.event import Event, EventTypes


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_coord_01",
        "event_type": EventTypes.COORDINATOR_DISPATCH,
        "source_agent": "coordinator",
        "payload": {
            "target_agent": "requirement-manager",
            "task_id": "task_001",
            "instruction": "Produce PRD",
        },
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=CoordinatorEventOutbox, **defaults)


class FakeCoordinatorEventOutboxStore(CoordinatorEventOutboxStore):
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
async def test_coordinator_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = CoordinatorEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.COORDINATOR_DISPATCH,
        source_agent="coordinator",
        payload={
            "target_agent": "requirement-manager",
            "task_id": "task_001",
            "instruction": "Produce PRD",
        },
        trace_id="trace-coordinator",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.COORDINATOR_DISPATCH
    assert row.source_agent == "coordinator"
    assert row.payload["target_agent"] == "requirement-manager"
    assert row.trace_id == "trace-coordinator"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_event_via_outbox_stages_before_publish():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeCoordinatorEventOutboxStore()
    agent = CoordinatorAgent(
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )
    event = Event.create(
        event_type=EventTypes.QA_RUN_REQUESTED,
        source_agent="coordinator",
        payload={"agent_name": "dev-agent", "level": "all"},
    )

    ok = await agent.publish_event_via_outbox(event)

    assert ok is True
    assert outbox_store.added == [event]
    publisher.publish.assert_awaited_once_with(event)
    bus.publish.assert_not_awaited()
    assert outbox_store.published == [event.event_id]
    assert outbox_store.failed == []


@pytest.mark.asyncio
async def test_publish_pending_coordinator_events_marks_failure_and_continues():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=[False, True])

    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store = FakeCoordinatorEventOutboxStore(rows=[failed_row, ok_row])
    agent = CoordinatorAgent(
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )

    result = await agent.publish_pending_coordinator_events(limit=2)

    assert outbox_store.last_limit == 2
    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    assert len(outbox_store.failed) == 1
    assert outbox_store.failed[0][0] == "evt_failed"
    assert outbox_store.published == ["evt_ok"]
    assert result == {"total": 2, "published": 1, "failed": 1}
