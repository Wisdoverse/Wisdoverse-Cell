"""Requirement outbox dispatcher tests."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.outbox_ports import RequirementEventOutboxStore
from agents.requirement_manager.models import RequirementEventOutbox
from agents.requirement_manager.service.agent import RequirementManagerAgent
from shared.schemas.event import Event, EventTypes


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_01",
        "event_type": EventTypes.REQUIREMENT_CONFIRMED,
        "source_agent": "requirement-manager",
        "payload": {
            "requirement_id": "req_123",
            "title": "Need onboarding",
            "priority": "HIGH",
            "category": "功能",
            "confirmed_by": "pm",
            "confirmed_at": datetime.now(UTC).isoformat(),
        },
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=RequirementEventOutbox, **defaults)


class FakeRequirementEventOutboxStore(RequirementEventOutboxStore):
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added: list[Event] = []
        self.staged: list[Event] = []
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.last_limit: int | None = None

    async def add(self, event: Event) -> None:
        self.added.append(event)

    async def stage(self, session: object, event: Event) -> None:
        self.staged.append(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


@pytest.mark.asyncio
async def test_publish_pending_requirement_events_marks_success():
    """Pending outbox rows are rebuilt as Events and marked published."""
    db = MagicMock()
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeRequirementEventOutboxStore(rows=[_outbox_row()])
    agent = RequirementManagerAgent(
        db=db,
        bus=bus,
        event_publisher=publisher,
        vectors=MagicMock(),
        outbox_store=outbox_store,
    )
    agent._mark_requirement_event_published = AsyncMock()
    agent._mark_requirement_event_failed = AsyncMock()

    result = await agent.publish_pending_requirement_events(limit=10)

    assert outbox_store.last_limit == 10
    publisher.publish.assert_awaited_once()
    bus.publish.assert_not_awaited()
    event = publisher.publish.call_args.args[0]
    assert event.event_id == "evt_01"
    assert event.event_type == EventTypes.REQUIREMENT_CONFIRMED
    assert event.payload["requirement_id"] == "req_123"
    agent._mark_requirement_event_published.assert_awaited_once_with(event)
    agent._mark_requirement_event_failed.assert_not_awaited()
    assert result == {"total": 1, "published": 1, "failed": 0}


@pytest.mark.asyncio
async def test_publish_pending_requirement_events_marks_failure_and_continues():
    """Dispatcher records failed publishes and keeps processing later rows."""
    db = MagicMock()
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=[RuntimeError("broker down"), True])
    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store = FakeRequirementEventOutboxStore(rows=[failed_row, ok_row])
    agent = RequirementManagerAgent(
        db=db,
        bus=bus,
        event_publisher=publisher,
        vectors=MagicMock(),
        outbox_store=outbox_store,
    )
    agent._mark_requirement_event_published = AsyncMock()
    agent._mark_requirement_event_failed = AsyncMock()

    result = await agent.publish_pending_requirement_events(limit=2)

    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    agent._mark_requirement_event_failed.assert_awaited_once()
    agent._mark_requirement_event_published.assert_awaited_once()
    assert result == {"total": 2, "published": 1, "failed": 1}
