"""User interaction gateway outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.gateways.user_interaction.core.event_ports import (
    UserInteractionEventOutboxStore,
)
from services.gateways.user_interaction.db.repository import (
    UserInteractionEventOutboxRepository,
)
from services.gateways.user_interaction.models import UserInteractionEventOutbox
from services.gateways.user_interaction.service.agent import ChatAgent
from shared.schemas.event import Event, EventTypes


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_chat_01",
        "event_type": EventTypes.SYNC_TRIGGER,
        "source_agent": "chat-agent",
        "payload": {"triggered_by": "chat_tool", "scope": "full"},
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=UserInteractionEventOutbox, **defaults)


class FakeUserInteractionEventOutboxStore(UserInteractionEventOutboxStore):
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
async def test_user_interaction_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = UserInteractionEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.SYNC_TRIGGER,
        source_agent="chat-agent",
        payload={"triggered_by": "chat_tool", "scope": "openproject"},
        trace_id="trace-chat",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.SYNC_TRIGGER
    assert row.source_agent == "chat-agent"
    assert row.payload["scope"] == "openproject"
    assert row.trace_id == "trace-chat"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_sync_trigger_stages_event_before_publish():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    outbox_store = FakeUserInteractionEventOutboxStore()
    agent = ChatAgent(bus=bus, outbox_store=outbox_store)

    ok = await agent.publish_sync_trigger(scope="full")

    assert ok is True
    assert len(outbox_store.added) == 1
    event = outbox_store.added[0]
    assert event.event_type == EventTypes.SYNC_TRIGGER
    assert event.source_agent == "chat-agent"
    assert event.payload["scope"] == "full"
    bus.connect.assert_awaited_once()
    bus.publish.assert_awaited_once_with(event)
    assert outbox_store.published == [event.event_id]
    assert outbox_store.failed == []


@pytest.mark.asyncio
async def test_publish_pending_user_interaction_events_marks_failure_and_continues():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(side_effect=[False, True])

    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok", payload={"scope": "openproject"})
    outbox_store = FakeUserInteractionEventOutboxStore(rows=[failed_row, ok_row])
    agent = ChatAgent(bus=bus, outbox_store=outbox_store)

    result = await agent.publish_pending_user_interaction_events(limit=2)

    assert outbox_store.last_limit == 2
    assert bus.publish.await_count == 2
    assert len(outbox_store.failed) == 1
    assert outbox_store.failed[0][0] == "evt_failed"
    assert outbox_store.published == ["evt_ok"]
    assert result == {"total": 2, "published": 1, "failed": 1}
