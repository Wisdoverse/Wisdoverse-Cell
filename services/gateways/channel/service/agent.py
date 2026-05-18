"""Channel Gateway Agent implementation."""
import asyncio
from typing import Any

from services.gateways.channel.core.event_use_cases import (
    SUBSCRIBED_EVENTS,
    ChannelGatewayEventUseCase,
)
from services.gateways.channel.core.lifecycle_use_cases import (
    ChannelGatewayLifecycleUseCase,
)
from shared.core import EventPublisher
from shared.infra.event_bus import event_bus as default_event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata
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
        return await self.channel_event_use_case().handle_event(event)

    def channel_event_use_case(self) -> ChannelGatewayEventUseCase:
        return ChannelGatewayEventUseCase(
            adapter_registry=self._adapter_registry,
            source_agent=self.agent_id,
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle direct requests (not used in event-driven architecture)."""
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return {"status": "ok"}

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the channel gateway boundary."""
        adapters = self._adapter_registry.list_all()
        return {
            "event_bus": bool(getattr(self._event_bus, "is_connected", False)),
            "database": self._db_manager is not None,
            "adapter_registry": self._adapter_registry is not None,
            "adapter_listeners": all(
                adapter.channel_id in self._listener_tasks for adapter in adapters
            ),
        }

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
        await self.channel_lifecycle_use_case().connect_adapters()

    async def _connect_adapter(self, adapter) -> None:
        """Connect a single adapter and start its listener."""
        await self.channel_lifecycle_use_case().connect_adapter(adapter)

    async def _disconnect_adapters(self) -> None:
        """Disconnect all adapters."""
        await self.channel_lifecycle_use_case().disconnect_adapters()

    async def _run_adapter_listener(self, adapter) -> None:
        """Listen for messages from an adapter."""
        await self.channel_lifecycle_use_case().run_adapter_listener(adapter)

    async def _publish_inbound_message(self, message) -> None:
        """Publish inbound message event."""
        await self.channel_lifecycle_use_case().publish_inbound_message(message)

    async def _publish_adapter_status(
        self, channel_id: str, status: str, error_message: str | None = None
    ) -> None:
        """Publish adapter status event."""
        await self.channel_lifecycle_use_case().publish_adapter_status(
            channel_id,
            status,
            error_message,
        )

    def channel_lifecycle_use_case(self) -> ChannelGatewayLifecycleUseCase:
        return ChannelGatewayLifecycleUseCase(
            adapter_registry=self._adapter_registry,
            publisher=self,
            listener_tasks=self._listener_tasks,
        )

    async def publish_pending_channel_events(self, limit: int = 100) -> dict[str, int]:
        """Retry pending channel gateway outbox events."""
        if self._outbox_store is None:
            raise RuntimeError("channel_outbox_store_not_started")

        rows = await self._outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            if await self._publish_staged_channel_event(event):
                published += 1
            else:
                failed += 1

        logger.info(
            "channel_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_channel_event_via_outbox(self, event: Event) -> bool:
        """Stage a channel gateway event, then publish after local commit."""
        if self._outbox_store is None:
            logger.error(
                "channel_outbox_unavailable",
                event_id=event.event_id,
                event_type=event.event_type,
            )
            return False

        try:
            await self._outbox_store.add(event)
        except Exception as exc:
            logger.error(
                "channel_outbox_stage_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False
        return await self._publish_staged_channel_event(event)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced channel event before EventBus delivery."""
        return await self.publish_channel_event_via_outbox(event)

    async def _publish_staged_channel_event(self, event: Event) -> bool:
        """Publish one event already persisted in the channel outbox."""
        try:
            await self._event_bus.connect()
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self._mark_channel_event_published(event)
            return True
        except Exception as exc:
            await self._mark_channel_event_failed(event, exc)
            logger.error(
                "channel_outbox_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a channel outbox row."""
        return Event(
            event_id=row.event_id,
            event_type=row.event_type,
            timestamp=row.created_at,
            source_agent=row.source_agent,
            payload=row.payload,
            schema_version=row.schema_version,
            metadata=EventMetadata(
                trace_id=row.trace_id,
                correlation_id=row.correlation_id,
                retry_count=row.retry_count,
            ),
        )

    async def _mark_channel_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published channel outbox event."""
        if self._outbox_store is None:
            logger.warning("channel_outbox_mark_published_skipped", event_id=event.event_id)
            return
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "channel_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_channel_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a channel outbox publish attempt."""
        if self._outbox_store is None:
            logger.warning(
                "channel_outbox_mark_failed_skipped",
                event_id=event.event_id,
                publish_error=str(error),
            )
            return
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "channel_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )


# Global singleton
_agent: ChannelGatewayAgent | None = None


def get_agent() -> ChannelGatewayAgent:
    """Get the singleton agent instance."""
    global _agent
    if _agent is None:
        from ..db.database import db_manager

        _agent = ChannelGatewayAgent(db=db_manager)
    return _agent
