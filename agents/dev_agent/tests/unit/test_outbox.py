"""Dev Agent outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.dev_agent.core.outbox_ports import DevEventOutboxStore
from agents.dev_agent.db.repository import DevEventOutboxRepository
from agents.dev_agent.models import DevAgentEventOutbox
from agents.dev_agent.service.agent import DevAgent
from shared.schemas.event import Event, EventTypes


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_dev_01",
        "event_type": EventTypes.DEV_MR_CREATED,
        "source_agent": "dev-agent",
        "payload": {"task_id": "dev_001", "mr_url": "https://gitlab/mr/1"},
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=DevAgentEventOutbox, **defaults)


class FakeDevEventOutboxStore(DevEventOutboxStore):
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
async def test_dev_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = DevEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.DEV_MR_CREATED,
        source_agent="dev-agent",
        payload={"task_id": "dev_001", "mr_url": "https://gitlab/mr/1"},
        trace_id="trace-dev",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.DEV_MR_CREATED
    assert row.source_agent == "dev-agent"
    assert row.payload["task_id"] == "dev_001"
    assert row.trace_id == "trace-dev"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_pending_dev_events_marks_success():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeDevEventOutboxStore(rows=[_outbox_row()])
    agent = DevAgent(
        bus=bus,
        event_publisher=publisher,
        outbox_store=outbox_store,
    )
    agent._mark_dev_event_published = AsyncMock()
    agent._mark_dev_event_failed = AsyncMock()

    result = await agent.publish_pending_dev_events(limit=5)

    assert outbox_store.last_limit == 5
    publisher.publish.assert_awaited_once()
    bus.publish.assert_not_awaited()
    event = publisher.publish.await_args.args[0]
    assert event.event_id == "evt_dev_01"
    assert event.event_type == EventTypes.DEV_MR_CREATED
    agent._mark_dev_event_published.assert_awaited_once_with(event)
    agent._mark_dev_event_failed.assert_not_awaited()
    assert result == {"total": 1, "published": 1, "failed": 0}


@pytest.mark.asyncio
async def test_publish_staged_dev_events_marks_failure_and_continues():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=[False, True])
    agent = DevAgent(bus=bus, event_publisher=publisher)
    agent._mark_dev_event_published = AsyncMock()
    agent._mark_dev_event_failed = AsyncMock()

    failed_event = Event.create(
        event_type=EventTypes.DEV_TASK_FAILED,
        source_agent="dev-agent",
        payload={"task_id": "dev_failed"},
    )
    ok_event = Event.create(
        event_type=EventTypes.QA_RUN_REQUESTED,
        source_agent="dev-agent",
        payload={"agent_name": "dev-agent"},
    )

    result = await agent.publish_staged_dev_events([failed_event, ok_event])

    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    agent._mark_dev_event_failed.assert_awaited_once()
    agent._mark_dev_event_published.assert_awaited_once_with(ok_event)
    assert result == {"total": 2, "published": 1, "failed": 1}
