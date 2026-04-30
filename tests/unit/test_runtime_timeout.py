import asyncio

import pytest

from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class HangingAgent(BaseAgent):
    async def handle_event(self, event):
        await asyncio.sleep(9999)
        return []

    async def handle_request(self, request):
        return {}


class FastAgent(BaseAgent):
    async def handle_event(self, event):
        return []

    async def handle_request(self, request):
        return {}


@pytest.fixture
def event():
    return Event(event_type="test.ping", source_agent="test", payload={})


@pytest.mark.asyncio
async def test_handle_event_timeout_raises(event):
    """handle_event that exceeds timeout should raise TimeoutError."""
    agent = HangingAgent(
        agent_id="test-hang",
        agent_name="Hanging Agent",
        subscribed_events=["test.ping"],
    )

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.1):
            await agent.handle_event(event)


@pytest.mark.asyncio
async def test_fast_handler_completes_within_timeout(event):
    """Normal handler should complete fine within timeout."""
    agent = FastAgent(
        agent_id="test-fast",
        agent_name="Fast Agent",
        subscribed_events=["test.ping"],
    )
    async with asyncio.timeout(5):
        result = await agent.handle_event(event)
    assert result == []
