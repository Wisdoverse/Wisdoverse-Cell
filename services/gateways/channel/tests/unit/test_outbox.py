"""Channel gateway outbox unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.gateways.channel.core.outbox_ports import ChannelGatewayEventOutboxStore
from services.gateways.channel.db.repository import ChannelGatewayEventOutboxRepository
from services.gateways.channel.models import ChannelGatewayEventOutbox
from services.gateways.channel.service.agent import ChannelGatewayAgent
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.schemas.event import Event


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_channel_01",
        "event_type": ChannelEventTypes.ADAPTER_STATUS,
        "source_agent": "channel-gateway",
        "payload": {
            "channel_id": "fake",
            "status": "connected",
            "error_message": None,
        },
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=ChannelGatewayEventOutbox, **defaults)


class FakeChannelGatewayEventOutboxStore(ChannelGatewayEventOutboxStore):
    def __init__(self, rows=None, add_error: Exception | None = None):
        self.rows = rows or []
        self.add_error = add_error
        self.added: list[Event] = []
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.last_limit: int | None = None

    async def add(self, event: Event) -> None:
        if self.add_error is not None:
            raise self.add_error
        self.added.append(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


@pytest.mark.asyncio
async def test_channel_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = ChannelGatewayEventOutboxRepository(session)
    event = Event.create(
        event_type=ChannelEventTypes.ADAPTER_STATUS,
        source_agent="channel-gateway",
        payload={
            "channel_id": "fake",
            "status": "connected",
            "error_message": None,
        },
        trace_id="trace-channel",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == ChannelEventTypes.ADAPTER_STATUS
    assert row.source_agent == "channel-gateway"
    assert row.payload["channel_id"] == "fake"
    assert row.trace_id == "trace-channel"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_channel_event_via_outbox_stages_before_publish():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    outbox_store = FakeChannelGatewayEventOutboxStore()
    agent = ChannelGatewayAgent(bus=bus, outbox_store=outbox_store)
    event = Event.create(
        event_type=ChannelEventTypes.ADAPTER_STATUS,
        source_agent="channel-gateway",
        payload={"channel_id": "fake", "status": "connected", "error_message": None},
    )

    ok = await agent.publish_channel_event_via_outbox(event)

    assert ok is True
    assert outbox_store.added == [event]
    bus.publish.assert_awaited_once_with(event)
    assert outbox_store.published == [event.event_id]
    assert outbox_store.failed == []


@pytest.mark.asyncio
async def test_publish_pending_channel_events_marks_failure_and_continues():
    bus = MagicMock()
    bus.connect = AsyncMock()
    bus.publish = AsyncMock(side_effect=[False, True])

    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store = FakeChannelGatewayEventOutboxStore(rows=[failed_row, ok_row])
    agent = ChannelGatewayAgent(bus=bus, outbox_store=outbox_store)

    result = await agent.publish_pending_channel_events(limit=2)

    assert outbox_store.last_limit == 2
    assert bus.publish.await_count == 2
    assert len(outbox_store.failed) == 1
    assert outbox_store.failed[0][0] == "evt_failed"
    assert outbox_store.published == ["evt_ok"]
    assert result == {"total": 2, "published": 1, "failed": 1}
