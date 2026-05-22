"""Tests for the channel gateway application facade."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.gateways.channel.core.application_facade import (
    ChannelGatewayApplicationFacade,
)
from services.gateways.channel.core.outbox_ports import ChannelGatewayEventOutboxStore
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.messaging.outbound.models.messages import DeliveryResult, OutboundMessage
from shared.schemas.event import Event


class _OutboxStore(ChannelGatewayEventOutboxStore):
    def __init__(self, rows=None) -> None:
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


class _Adapter:
    channel_id = "fake"

    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        self.sent.append(message)
        return DeliveryResult(success=True, platform_message_id="platform_msg_123")

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def listen(self) -> AsyncIterator[Any]:
        return
        yield


class _Registry:
    def __init__(self, adapter: _Adapter | None = None) -> None:
        self.adapter = adapter

    def get(self, channel_id: str):
        if self.adapter and channel_id == self.adapter.channel_id:
            return self.adapter
        return None

    def list_all(self):
        return [self.adapter] if self.adapter else []


class _EventFactory:
    agent_id = "channel-gateway"

    def __init__(self) -> None:
        self.published: list[Event] = []

    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent=self.agent_id,
            payload=payload,
            trace_id=trace_id,
        )

    async def publish_channel_event_via_outbox(self, event: Event) -> bool:
        self.published.append(event)
        return True


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
    return MagicMock(**defaults)


def _facade(
    *,
    registry: _Registry | None = None,
    event_factory: _EventFactory | None = None,
    event_bus: MagicMock | None = None,
    event_publisher: MagicMock | None = None,
    outbox_store: _OutboxStore | None = None,
    db_manager=object(),
    standard_request_handler: AsyncMock | None = None,
) -> ChannelGatewayApplicationFacade:
    event_bus = event_bus or MagicMock(is_connected=True)
    event_bus.connect = AsyncMock()
    event_publisher = event_publisher or MagicMock()
    event_publisher.publish = AsyncMock(return_value=True)
    return ChannelGatewayApplicationFacade(
        agent_id="channel-gateway",
        standard_request_handler=standard_request_handler or AsyncMock(return_value=None),
        adapter_registry=registry or _Registry(),
        listener_tasks={},
        event_factory=event_factory or _EventFactory(),
        event_bus=event_bus,
        event_publisher=event_publisher,
        db_manager_provider=lambda: db_manager,
        outbox_store_provider=lambda: outbox_store,
    )


@pytest.mark.asyncio
async def test_channel_application_facade_dispatches_event_use_case() -> None:
    adapter = _Adapter()
    message = OutboundMessage(
        channel_id="fake",
        target_chat_id="chat_123",
        content="hello",
        trace_id="trace-message",
    )
    event = Event.create(
        event_type=ChannelEventTypes.MESSAGE_OUTBOUND,
        source_agent="test-agent",
        payload={"message": message.model_dump(mode="json")},
        trace_id="trace-event",
    )

    result = await _facade(registry=_Registry(adapter)).handle_event(event)

    assert adapter.sent == [message]
    assert result[0].event_type == ChannelEventTypes.MESSAGE_DELIVERED
    assert result[0].metadata.trace_id == "trace-event"


@pytest.mark.asyncio
async def test_channel_application_facade_preserves_standard_request_boundary() -> None:
    standard = AsyncMock(return_value={"status": "standard"})

    result = await _facade(standard_request_handler=standard).handle_request(
        {"action": "describe"}
    )

    assert result == {"status": "standard"}
    standard.assert_awaited_once_with({"action": "describe"})


@pytest.mark.asyncio
async def test_channel_application_facade_reports_health_from_runtime_dependencies() -> None:
    adapter = _Adapter()
    registry = _Registry(adapter)
    event_bus = MagicMock(is_connected=True)
    event_bus.connect = AsyncMock()
    facade = ChannelGatewayApplicationFacade(
        agent_id="channel-gateway",
        standard_request_handler=AsyncMock(return_value=None),
        adapter_registry=registry,
        listener_tasks={"fake": MagicMock()},
        event_factory=_EventFactory(),
        event_bus=event_bus,
        event_publisher=MagicMock(),
        db_manager_provider=lambda: object(),
        outbox_store_provider=lambda: None,
    )

    assert await facade.health_check() == {
        "event_bus": True,
        "database": True,
        "adapter_registry": True,
        "adapter_listeners": True,
    }


@pytest.mark.asyncio
async def test_channel_application_facade_delegates_lifecycle_use_case() -> None:
    adapter = _Adapter()
    event_factory = _EventFactory()
    facade = _facade(registry=_Registry(adapter), event_factory=event_factory)

    await facade.connect_adapter(adapter)

    assert event_factory.published[0].event_type == ChannelEventTypes.ADAPTER_STATUS
    assert event_factory.published[0].payload["status"] == "connected"


@pytest.mark.asyncio
async def test_channel_application_facade_delegates_outbox_delivery() -> None:
    event_bus = MagicMock(is_connected=False)
    event_bus.connect = AsyncMock()
    event_publisher = MagicMock()
    event_publisher.publish = AsyncMock(return_value=True)
    outbox_store = _OutboxStore(rows=[_outbox_row(event_id="evt_pending")])
    facade = _facade(
        event_bus=event_bus,
        event_publisher=event_publisher,
        outbox_store=outbox_store,
    )
    event = Event.create(
        event_type=ChannelEventTypes.ADAPTER_STATUS,
        source_agent="channel-gateway",
        payload={"channel_id": "fake", "status": "connected", "error_message": None},
    )

    assert await facade.publish_channel_event_via_outbox(event) is True
    result = await facade.publish_pending_channel_events(limit=1)

    assert outbox_store.added == [event]
    assert outbox_store.last_limit == 1
    assert result == {"total": 1, "published": 1, "failed": 0}
    assert event_publisher.publish.await_count == 2
