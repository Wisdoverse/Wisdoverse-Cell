"""Tests for channel gateway agent."""
from datetime import UTC, datetime
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.gateways.channel.service.agent import (
    ChannelGatewayAgent,
    get_agent,
)
from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import ChannelCapability, ChannelStatus, ChatType
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.messaging.outbound.models.events import (
    CHANNEL_EVENT_PAYLOAD_MODELS,
    ChannelEventTypes,
)
from shared.messaging.outbound.models.messages import (
    ChatContext,
    DeliveryResult,
    InboundMessage,
    MessageAuthor,
    OutboundMessage,
)
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class FakeAdapter(BaseChannelAdapter):
    channel_id = "fake"
    channel_name = "Fake"
    status = ChannelStatus.STABLE
    capabilities = {ChannelCapability.TEXT}

    def __init__(self, result: DeliveryResult | None = None, error: Exception | None = None):
        self.result = result or DeliveryResult(
            success=True,
            platform_message_id="platform_msg_123",
        )
        self.error = error
        self.sent_messages: list[OutboundMessage] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        self.sent_messages.append(message)
        if self.error is not None:
            raise self.error
        return self.result

    async def listen(self) -> AsyncIterator[InboundMessage]:
        return
        yield


class TestChannelGatewayAgentClass:
    def test_inherits_from_base_agent(self):
        agent = ChannelGatewayAgent()
        assert isinstance(agent, BaseAgent)

    def test_agent_id_is_kebab_case(self):
        agent = ChannelGatewayAgent()
        assert agent.agent_id == "channel-gateway"
        assert "-" in agent.agent_id

    def test_agent_name(self):
        agent = ChannelGatewayAgent()
        assert agent.agent_name == "Channel Gateway Agent"

    def test_subscribed_events(self):
        agent = ChannelGatewayAgent()
        assert ChannelEventTypes.MESSAGE_OUTBOUND in agent.subscribed_events

    def test_published_events(self):
        agent = ChannelGatewayAgent()
        assert ChannelEventTypes.MESSAGE_INBOUND in agent.published_events
        assert ChannelEventTypes.MESSAGE_DELIVERED in agent.published_events
        assert ChannelEventTypes.ADAPTER_STATUS in agent.published_events

    def test_channel_event_types_have_payload_models(self):
        event_types = {
            value
            for name, value in vars(ChannelEventTypes).items()
            if name.isupper() and isinstance(value, str)
        }

        assert event_types == set(CHANNEL_EVENT_PAYLOAD_MODELS)


class TestChannelGatewayAgentDependencyInjection:
    def test_accepts_custom_event_bus(self):
        mock_bus = MagicMock()
        agent = ChannelGatewayAgent(bus=mock_bus)
        assert agent._event_bus is mock_bus

    def test_accepts_custom_adapter_registry(self):
        registry = AdapterRegistry()
        agent = ChannelGatewayAgent(adapter_registry=registry)
        assert agent._adapter_registry is registry

    @pytest.mark.asyncio
    async def test_startup_uses_runtime_event_loop_boundary(self):
        mock_bus = AsyncMock()
        mock_bus.connect = AsyncMock()
        mock_bus.disconnect = AsyncMock()
        agent = ChannelGatewayAgent(
            bus=mock_bus,
            adapter_registry=AdapterRegistry(),
        )

        await agent.startup()
        await agent.shutdown()

        assert agent._consumer_task is None
        mock_bus.connect.assert_awaited_once()
        mock_bus.disconnect.assert_awaited_once()


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_standard_describe_action(self):
        agent = ChannelGatewayAgent()

        result = await agent.handle_request({"action": "describe"})

        assert result["agent_id"] == "channel-gateway"
        assert result["agent_name"] == "Channel Gateway Agent"

    @pytest.mark.asyncio
    async def test_standard_health_action_reports_gateway_dependencies(self):
        mock_bus = MagicMock()
        mock_bus.is_connected = True
        agent = ChannelGatewayAgent(
            bus=mock_bus,
            adapter_registry=AdapterRegistry(),
        )

        result = await agent.handle_request({"action": "health"})

        assert result == {
            "agent_id": "channel-gateway",
            "checks": {
                "event_bus": True,
                "adapter_registry": True,
                "adapter_listeners": True,
            },
        }

    @pytest.mark.asyncio
    async def test_unknown_action_returns_ok(self):
        agent = ChannelGatewayAgent()

        result = await agent.handle_request({"action": "unknown"})

        assert result == {"status": "ok"}


class TestEventCreation:
    def test_create_event_sets_source_agent(self):
        agent = ChannelGatewayAgent()
        event = agent.create_event(
            event_type=ChannelEventTypes.MESSAGE_DELIVERED,
            payload={"message_id": "msg_123"},
        )
        assert event.source_agent == "channel-gateway"
        assert event.event_type == ChannelEventTypes.MESSAGE_DELIVERED

    @pytest.mark.asyncio
    async def test_publish_inbound_message_uses_json_payload_contract(self):
        mock_bus = AsyncMock()
        agent = ChannelGatewayAgent(
            bus=mock_bus,
            adapter_registry=AdapterRegistry(),
        )
        message = InboundMessage(
            channel_id="fake",
            platform_message_id="platform_msg_123",
            author=MessageAuthor(platform_user_id="ou_user"),
            chat=ChatContext(
                platform_chat_id="chat_123",
                chat_type=ChatType.GROUP,
            ),
            content="hello",
            timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        )

        await agent._publish_inbound_message(message)

        mock_bus.publish.assert_awaited_once()
        event = mock_bus.publish.await_args.args[0]
        assert event.event_type == ChannelEventTypes.MESSAGE_INBOUND
        assert event.payload["message"]["timestamp"] == "2026-05-04T12:00:00Z"

    @pytest.mark.asyncio
    async def test_publish_adapter_status_uses_registered_payload_contract(self):
        mock_bus = AsyncMock()
        agent = ChannelGatewayAgent(
            bus=mock_bus,
            adapter_registry=AdapterRegistry(),
        )

        await agent._publish_adapter_status("fake", "connected")

        mock_bus.publish.assert_awaited_once()
        event = mock_bus.publish.await_args.args[0]
        assert event.event_type == ChannelEventTypes.ADAPTER_STATUS
        assert event.payload == {
            "channel_id": "fake",
            "status": "connected",
            "error_message": None,
        }


class TestOutboundEventHandling:
    @pytest.mark.asyncio
    async def test_routes_outbound_message_to_registered_adapter(self):
        registry = AdapterRegistry()
        adapter = FakeAdapter()
        registry.register(adapter)
        agent = ChannelGatewayAgent(adapter_registry=registry)
        message = OutboundMessage(
            channel_id="fake",
            target_chat_id="chat_123",
            content="hello",
            trace_id="trc_message",
        )
        event = Event.create(
            event_type=ChannelEventTypes.MESSAGE_OUTBOUND,
            source_agent="test-agent",
            payload={"message": message.model_dump(mode="json")},
            trace_id="trc_event",
        )

        new_events = await agent.handle_event(event)

        assert adapter.sent_messages == [message]
        assert len(new_events) == 1
        delivered = new_events[0]
        assert delivered.event_type == ChannelEventTypes.MESSAGE_DELIVERED
        assert delivered.source_agent == "channel-gateway"
        assert delivered.metadata.trace_id == "trc_event"
        assert delivered.payload["message_id"] == message.message_id
        assert delivered.payload["channel_id"] == "fake"
        assert delivered.payload["result"]["success"] is True
        assert delivered.payload["result"]["platform_message_id"] == "platform_msg_123"

    @pytest.mark.asyncio
    async def test_missing_adapter_returns_failed_delivery_event(self):
        agent = ChannelGatewayAgent(adapter_registry=AdapterRegistry())
        message = OutboundMessage(
            channel_id="missing",
            target_chat_id="chat_123",
            content="hello",
            trace_id="trc_message",
        )
        event = Event.create(
            event_type=ChannelEventTypes.MESSAGE_OUTBOUND,
            source_agent="test-agent",
            payload={"message": message.model_dump(mode="json")},
        )

        new_events = await agent.handle_event(event)

        assert len(new_events) == 1
        delivered = new_events[0]
        assert delivered.metadata.trace_id == "trc_message"
        assert delivered.payload["message_id"] == message.message_id
        assert delivered.payload["result"]["success"] is False
        assert delivered.payload["result"]["error_code"] == "adapter_not_found"

    @pytest.mark.asyncio
    async def test_adapter_exception_returns_failed_delivery_event(self):
        registry = AdapterRegistry()
        registry.register(FakeAdapter(error=RuntimeError("delivery failed")))
        agent = ChannelGatewayAgent(adapter_registry=registry)
        message = OutboundMessage(
            channel_id="fake",
            target_chat_id="chat_123",
            content="hello",
        )
        event = Event.create(
            event_type=ChannelEventTypes.MESSAGE_OUTBOUND,
            source_agent="test-agent",
            payload={"message": message.model_dump(mode="json")},
        )

        new_events = await agent.handle_event(event)

        assert len(new_events) == 1
        delivered = new_events[0]
        assert delivered.payload["result"]["success"] is False
        assert delivered.payload["result"]["error_code"] == "RuntimeError"
        assert delivered.payload["result"]["error_message"] == "delivery failed"


class TestGetAgent:
    def test_returns_singleton(self):
        # Reset the global singleton for testing
        import services.gateways.channel.service.agent as agent_module
        agent_module._agent = None

        agent1 = get_agent()
        agent2 = get_agent()
        assert agent1 is agent2
