from datetime import UTC, datetime
from typing import AsyncIterator

import pytest

from services.gateways.channel.core.lifecycle_use_cases import (
    ChannelGatewayLifecycleUseCase,
)
from shared.messaging.outbound.core.enums import ChatType
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.messaging.outbound.models.messages import (
    ChatContext,
    InboundMessage,
    MessageAuthor,
)
from shared.schemas.event import Event


class _Publisher:
    def __init__(self, success: bool = True):
        self.success = success
        self.events: list[Event] = []

    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="channel-gateway",
            payload=payload,
            trace_id=trace_id,
        )

    async def publish_channel_event_via_outbox(self, event: Event) -> bool:
        self.events.append(event)
        return self.success


class _Registry:
    def __init__(self, adapters):
        self._adapters = adapters

    def list_all(self):
        return self._adapters


class _Adapter:
    def __init__(
        self,
        *,
        channel_id: str = "fake",
        messages=None,
        listen_error: Exception | None = None,
    ):
        self.channel_id = channel_id
        self.messages = messages or []
        self.listen_error = listen_error
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def listen(self) -> AsyncIterator[InboundMessage]:
        if self.listen_error is not None:
            raise self.listen_error
        for message in self.messages:
            yield message


def _message() -> InboundMessage:
    return InboundMessage(
        channel_id="fake",
        platform_message_id="platform_msg_123",
        author=MessageAuthor(platform_user_id="ou_user"),
        chat=ChatContext(platform_chat_id="chat_123", chat_type=ChatType.GROUP),
        content="hello",
        timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    )


def _use_case(*, adapters=None, publisher=None, listener_tasks=None):
    publisher = publisher or _Publisher()
    listener_tasks = listener_tasks if listener_tasks is not None else {}
    use_case = ChannelGatewayLifecycleUseCase(
        adapter_registry=_Registry(adapters or []),
        publisher=publisher,
        listener_tasks=listener_tasks,
    )
    return use_case, publisher, listener_tasks


@pytest.mark.asyncio
async def test_publish_inbound_message_uses_json_payload_contract() -> None:
    use_case, publisher, _ = _use_case()

    await use_case.publish_inbound_message(_message())

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.event_type == ChannelEventTypes.MESSAGE_INBOUND
    assert event.source_agent == "channel-gateway"
    assert event.payload["message"]["timestamp"] == "2026-05-04T12:00:00Z"


@pytest.mark.asyncio
async def test_publish_adapter_status_uses_registered_payload_contract() -> None:
    use_case, publisher, _ = _use_case()

    await use_case.publish_adapter_status("fake", "connected")

    assert publisher.events[0].event_type == ChannelEventTypes.ADAPTER_STATUS
    assert publisher.events[0].payload == {
        "channel_id": "fake",
        "status": "connected",
        "error_message": None,
    }


@pytest.mark.asyncio
async def test_connect_adapter_publishes_status_and_starts_listener() -> None:
    adapter = _Adapter(messages=[])
    listener_tasks = {}
    use_case, publisher, _ = _use_case(
        adapters=[adapter],
        listener_tasks=listener_tasks,
    )

    await use_case.connect_adapter(adapter)

    assert adapter.connected is True
    assert publisher.events[0].event_type == ChannelEventTypes.ADAPTER_STATUS
    assert publisher.events[0].payload["status"] == "connected"
    assert "fake" in listener_tasks
    await listener_tasks["fake"]


@pytest.mark.asyncio
async def test_disconnect_adapters_publishes_disconnected_status() -> None:
    adapter = _Adapter()
    use_case, publisher, _ = _use_case(adapters=[adapter])

    await use_case.disconnect_adapters()

    assert adapter.disconnected is True
    assert publisher.events[0].event_type == ChannelEventTypes.ADAPTER_STATUS
    assert publisher.events[0].payload["status"] == "disconnected"


@pytest.mark.asyncio
async def test_listener_failure_publishes_error_status() -> None:
    adapter = _Adapter(listen_error=RuntimeError("listen failed"))
    use_case, publisher, _ = _use_case(adapters=[adapter])

    await use_case.run_adapter_listener(adapter)

    assert publisher.events[0].event_type == ChannelEventTypes.ADAPTER_STATUS
    assert publisher.events[0].payload == {
        "channel_id": "fake",
        "status": "error",
        "error_message": "listen failed",
    }
