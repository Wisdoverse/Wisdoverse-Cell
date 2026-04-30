"""Tests for channel gateway agent."""
from unittest.mock import MagicMock

from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.messaging.outbound.service.agent import (
    ChannelGatewayAgent,
    get_agent,
)
from shared.schemas.agent import BaseAgent


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


class TestChannelGatewayAgentDependencyInjection:
    def test_accepts_custom_event_bus(self):
        mock_bus = MagicMock()
        agent = ChannelGatewayAgent(bus=mock_bus)
        assert agent._event_bus is mock_bus


class TestEventCreation:
    def test_create_event_sets_source_agent(self):
        agent = ChannelGatewayAgent()
        event = agent.create_event(
            event_type=ChannelEventTypes.MESSAGE_DELIVERED,
            payload={"message_id": "msg_123"},
        )
        assert event.source_agent == "channel-gateway"
        assert event.event_type == ChannelEventTypes.MESSAGE_DELIVERED


class TestGetAgent:
    def test_returns_singleton(self):
        # Reset the global singleton for testing
        import shared.messaging.outbound.service.agent as agent_module
        agent_module._agent = None

        agent1 = get_agent()
        agent2 = get_agent()
        assert agent1 is agent2
