"""Channel Gateway Agent implementation."""
import asyncio
from typing import Any

from services.gateways.channel.core.application_facade import ChannelGatewayApplicationFacade
from services.gateways.channel.core.event_use_cases import SUBSCRIBED_EVENTS
from shared.core import EventPublisher
from shared.infra.event_bus import event_bus as default_event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from ..core.outbox_ports import ChannelGatewayEventOutboxStore
from ..db.outbox_store import SqlAlchemyChannelGatewayEventOutboxStore

logger = get_logger(__name__)


class ChannelGatewayAgent(BaseAgent):
    """Agent for managing multi-platform messaging channels."""

    def __init__(
        self,
        bus=None,
        adapter_registry: AdapterRegistry | None = None,
        db=None,
        event_publisher: EventPublisher | None = None,
        outbox_store: ChannelGatewayEventOutboxStore | None = None,
    ):
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
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._adapter_registry = adapter_registry or AdapterRegistry.default()
        self._db_manager = db
        self._outbox_store = outbox_store
        if self._outbox_store is None and self._db_manager is not None:
            self._outbox_store = SqlAlchemyChannelGatewayEventOutboxStore(
                self._db_manager
            )
        self._consumer_task: asyncio.Task | None = None
        self._listener_tasks: dict[str, asyncio.Task] = {}
        self._application = ChannelGatewayApplicationFacade(
            agent_id=self.agent_id,
            standard_request_handler=self.handle_standard_request,
            adapter_registry=self._adapter_registry,
            listener_tasks=self._listener_tasks,
            event_factory=self,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
            db_manager_provider=lambda: self._db_manager,
            outbox_store_provider=lambda: self._outbox_store,
        )

    async def startup(self) -> None:
        """Initialize the agent and connect adapters."""
        logger.info("starting_channel_gateway_agent")

        # Connect to event bus
        await self._event_bus.connect()

        if self._db_manager is not None:
            from shared.config import settings

            if settings.app_env == "development":
                await self._db_manager.create_tables()
                logger.info("channel_gateway_db_initialized")

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

        if self._db_manager is not None:
            await self._db_manager.close()

        logger.info("channel_gateway_agent_stopped")

    async def handle_event(self, event: Event) -> list[Event]:
        """Handle incoming events."""
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle direct requests (not used in event-driven architecture)."""
        return await self._application.handle_request(request)

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the channel gateway boundary."""
        return await self._application.health_check()

    async def _run_event_loop(self) -> None:
        """Event consumer loop."""
        async for event in self._event_bus.subscribe(self.subscribed_events):
            try:
                new_events = await self.handle_event(event)
                for e in new_events:
                    await self.publish_channel_event_via_outbox(e)
            except Exception as e:
                logger.error(
                    "event_handling_failed",
                    event_id=event.event_id,
                    error=str(e),
                )

    async def _connect_adapters(self) -> None:
        """Connect all registered adapters."""
        await self._application.connect_adapters()

    async def _connect_adapter(self, adapter) -> None:
        """Connect a single adapter and start its listener."""
        await self._application.connect_adapter(adapter)

    async def _disconnect_adapters(self) -> None:
        """Disconnect all adapters."""
        await self._application.disconnect_adapters()

    async def _run_adapter_listener(self, adapter) -> None:
        """Listen for messages from an adapter."""
        await self._application.run_adapter_listener(adapter)

    async def _publish_inbound_message(self, message) -> None:
        """Publish inbound message event."""
        await self._application.publish_inbound_message(message)

    async def _publish_adapter_status(
        self, channel_id: str, status: str, error_message: str | None = None
    ) -> None:
        """Publish adapter status event."""
        await self._application.publish_adapter_status(
            channel_id,
            status,
            error_message,
        )

    async def publish_pending_channel_events(self, limit: int = 100) -> dict[str, int]:
        """Retry pending channel gateway outbox events."""
        return await self._application.publish_pending_channel_events(limit=limit)

    async def publish_channel_event_via_outbox(self, event: Event) -> bool:
        """Stage a channel gateway event, then publish after local commit."""
        return await self._application.publish_channel_event_via_outbox(event)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced channel event before EventBus delivery."""
        return await self.publish_channel_event_via_outbox(event)

    async def _publish_staged_channel_event(self, event: Event) -> bool:
        """Publish one event already persisted in the channel outbox."""
        return await self._application.publish_staged_channel_event(event)


# Global singleton
_agent: ChannelGatewayAgent | None = None


def get_agent() -> ChannelGatewayAgent:
    """Get the singleton agent instance."""
    global _agent
    if _agent is None:
        from ..db.database import db_manager

        _agent = ChannelGatewayAgent(db=db_manager)
    return _agent
