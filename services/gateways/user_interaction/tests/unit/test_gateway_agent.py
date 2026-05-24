"""Tests for the user-interaction gateway runtime shell."""

import pytest

from services.gateways.user_interaction.service.agent import UserInteractionGatewayAgent
from shared.app import UNKNOWN_ACTION_ERROR_CODE
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_gateway_agent_has_no_product_event_subscriptions() -> None:
    agent = UserInteractionGatewayAgent()

    assert agent.agent_id == "user-interaction-gateway"
    assert agent.subscribed_events == []
    assert agent.published_events == []
    assert await agent.health_check() == {"gateway": True}


@pytest.mark.asyncio
async def test_gateway_agent_does_not_handle_product_requests() -> None:
    agent = UserInteractionGatewayAgent()

    assert await agent.handle_request({"action": "chat"}) == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }


@pytest.mark.asyncio
async def test_gateway_agent_ignores_events() -> None:
    agent = UserInteractionGatewayAgent()
    event = Event.create(
        event_type=EventTypes.COORDINATOR_RESPONSE,
        source_agent="coordinator",
        payload={},
    )

    assert await agent.handle_event(event) == []
