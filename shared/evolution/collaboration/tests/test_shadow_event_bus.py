import pytest

from shared.evolution.collaboration.shadow_event_bus import ShadowEventBus
from shared.schemas.event import Event


@pytest.mark.asyncio
class TestShadowEventBus:
    async def test_publish_records_event(self):
        bus = ShadowEventBus()
        event = Event.create(event_type="test.event", source_agent="test", payload={"k": "v"})
        await bus.publish(event)
        assert len(bus.published_events) == 1
        assert bus.published_events[0].event_type == "test.event"

    async def test_multiple_publishes(self):
        bus = ShadowEventBus()
        for i in range(5):
            await bus.publish(Event.create(event_type=f"test.{i}", source_agent="test", payload={}))
        assert len(bus.published_events) == 5

    async def test_connect_is_noop(self):
        bus = ShadowEventBus()
        await bus.connect()  # Should not raise

    async def test_disconnect_is_noop(self):
        bus = ShadowEventBus()
        await bus.disconnect()  # Should not raise

    async def test_reset_clears(self):
        bus = ShadowEventBus()
        await bus.publish(Event.create(event_type="test.event", source_agent="t", payload={}))
        bus.reset()
        assert len(bus.published_events) == 0
