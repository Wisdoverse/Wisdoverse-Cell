"""Channel Gateway Agent implementation."""
import asyncio
from typing import Any

from services.gateways.channel.service.event_handlers import (
    SUBSCRIBED_EVENTS,
    dispatch_event,
)
from shared.infra.event_bus import event_bus as default_event_bus
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class ChannelGatewayAgent(BaseAgent):
    """Agent for managing multi-platform messaging channels."""

    def __init__(self, bus=None, adapter_registry: AdapterRegistry | None = None):
        super().__init__(
            agent_id="channel-gateway",
            agent_name="Channel Gateway Agent",
            subscribed_events=SUBSCRIBED_EVENTS,
            published_events=[
                ChannelEventTypes.MESSAGE_INBOUND,
                ChannelEventTypes.MESSAGE_DELIVERED,
                ChannelEventTypes.ADAPTER_STATUS,
            ],
        )
        self._event_bus = bus or default_event_bus
        self._adapter_registry = adapter_registry or AdapterRegistry.default()
        self._consumer_task: asyncio.Task | None = None
        self._listener_tasks: dict[str, asyncio.Task] = {}

    async def startup(self) -> None:
        """Initialize the agent and connect adapters."""
        logger.info("starting_channel_gateway_agent")

        # Connect to event bus
        await self._event_bus.connect()

        # Connect all registered adapters
        await self._connect_adapters()

        logger.info("channel_gateway_agent_started")

    async def shutdown(self) -> None:
        """Shutdown the agent and disconnect adapters."""
        logger.info("shutting_down_channel_gateway_agent")

        # Cancel event consumer
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # Cancel listener tasks
        for task in self._listener_tasks.values():
            task.cancel()

        # Disconnect adapters
        await self._disconnect_adapters()

        # Disconnect from event bus
        await self._event_bus.disconnect()

        logger.info("channel_gateway_agent_stopped")

    async def handle_event(self, event: Event) -> list[Event]:
        """Handle incoming events."""
        return await dispatch_event(self, event)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle direct requests (not used in event-driven architecture)."""
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return {"status": "ok"}

    async def _run_event_loop(self) -> None:
        """Event consumer loop."""
        async for event in self._event_bus.subscribe(self.subscribed_events):
            try:
                new_events = await self.handle_event(event)
                for e in new_events:
                    await self._event_bus.publish(e)
            except Exception as e:
                logger.error(
                    "event_handling_failed",
                    event_id=event.event_id,
                    error=str(e),
                )

    async def _connect_adapters(self) -> None:
        """Connect all registered adapters."""
        adapters = self._adapter_registry.list_all()
        tasks = [self._connect_adapter(a) for a in adapters]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _connect_adapter(self, adapter) -> None:
        """Connect a single adapter and start its listener."""
        try:
            await adapter.connect()
            await self._publish_adapter_status(adapter.channel_id, "connected")

            # Start listener task
            task = asyncio.create_task(self._run_adapter_listener(adapter))
            self._listener_tasks[adapter.channel_id] = task

            logger.info("adapter_connected", channel_id=adapter.channel_id)
        except Exception as e:
            logger.error(
                "adapter_connection_failed",
                channel_id=adapter.channel_id,
                error=str(e),
            )
            await self._publish_adapter_status(
                adapter.channel_id, "error", str(e)
            )

    async def _disconnect_adapters(self) -> None:
        """Disconnect all adapters."""
        adapters = self._adapter_registry.list_all()
        for adapter in adapters:
            try:
                await adapter.disconnect()
                await self._publish_adapter_status(adapter.channel_id, "disconnected")
            except Exception as e:
                logger.error(
                    "adapter_disconnect_failed",
                    channel_id=adapter.channel_id,
                    error=str(e),
                )

    async def _run_adapter_listener(self, adapter) -> None:
        """Listen for messages from an adapter."""
        try:
            async for message in adapter.listen():
                await self._publish_inbound_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                "adapter_listener_failed",
                channel_id=adapter.channel_id,
                error=str(e),
            )
            await self._publish_adapter_status(adapter.channel_id, "error", str(e))

    async def _publish_inbound_message(self, message) -> None:
        """Publish inbound message event."""
        event = self.create_event(
            event_type=ChannelEventTypes.MESSAGE_INBOUND,
            payload={"message": message.model_dump()},
        )
        try:
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error("publish_inbound_failed", error=str(e))

    async def _publish_adapter_status(
        self, channel_id: str, status: str, error_message: str | None = None
    ) -> None:
        """Publish adapter status event."""
        event = self.create_event(
            event_type=ChannelEventTypes.ADAPTER_STATUS,
            payload={
                "channel_id": channel_id,
                "status": status,
                "error_message": error_message,
            },
        )
        try:
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error("publish_status_failed", error=str(e))


# Global singleton
_agent: ChannelGatewayAgent | None = None


def get_agent() -> ChannelGatewayAgent:
    """Get the singleton agent instance."""
    global _agent
    if _agent is None:
        _agent = ChannelGatewayAgent()
    return _agent
