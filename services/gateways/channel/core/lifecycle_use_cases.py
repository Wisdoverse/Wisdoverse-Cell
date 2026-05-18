"""Application use cases for channel gateway adapter lifecycle."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, MutableMapping
from typing import Any, Protocol

from shared.messaging.outbound.models.events import (
    AdapterStatusPayload,
    ChannelEventTypes,
    MessageInboundPayload,
)
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger("channel_gateway.lifecycle")


class ChannelLifecycleAdapterPort(Protocol):
    """Channel adapter operations required by lifecycle orchestration."""

    channel_id: str

    async def connect(self) -> None:
        """Connect the adapter to its platform."""

    async def disconnect(self) -> None:
        """Disconnect the adapter from its platform."""

    def listen(self) -> AsyncIterator[Any]:
        """Yield inbound platform messages."""


class ChannelLifecycleAdapterRegistryPort(Protocol):
    """Adapter registry operations required by lifecycle orchestration."""

    def list_all(self) -> list[ChannelLifecycleAdapterPort]:
        """Return all configured adapters."""


class ChannelLifecyclePublisherPort(Protocol):
    """Channel event publisher boundary owned by the service shell."""

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> Event:
        """Create an event with channel-gateway identity."""

    async def publish_channel_event_via_outbox(self, event: Event) -> bool:
        """Stage and publish one channel event via the durable outbox."""


class ChannelGatewayLifecycleUseCase:
    """Connect adapters and publish lifecycle/inbound channel events."""

    def __init__(
        self,
        *,
        adapter_registry: ChannelLifecycleAdapterRegistryPort,
        publisher: ChannelLifecyclePublisherPort,
        listener_tasks: MutableMapping[str, asyncio.Task],
    ) -> None:
        self._adapter_registry = adapter_registry
        self._publisher = publisher
        self._listener_tasks = listener_tasks

    async def connect_adapters(self) -> None:
        adapters = self._adapter_registry.list_all()
        tasks = [self.connect_adapter(adapter) for adapter in adapters]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def connect_adapter(self, adapter: ChannelLifecycleAdapterPort) -> None:
        try:
            await adapter.connect()
            await self.publish_adapter_status(adapter.channel_id, "connected")

            task = asyncio.create_task(self.run_adapter_listener(adapter))
            self._listener_tasks[adapter.channel_id] = task

            logger.info("adapter_connected", channel_id=adapter.channel_id)
        except Exception as exc:
            logger.error(
                "adapter_connection_failed",
                channel_id=adapter.channel_id,
                error=str(exc),
            )
            await self.publish_adapter_status(adapter.channel_id, "error", str(exc))

    async def disconnect_adapters(self) -> None:
        adapters = self._adapter_registry.list_all()
        for adapter in adapters:
            try:
                await adapter.disconnect()
                await self.publish_adapter_status(adapter.channel_id, "disconnected")
            except Exception as exc:
                logger.error(
                    "adapter_disconnect_failed",
                    channel_id=adapter.channel_id,
                    error=str(exc),
                )

    async def run_adapter_listener(self, adapter: ChannelLifecycleAdapterPort) -> None:
        try:
            async for message in adapter.listen():
                await self.publish_inbound_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(
                "adapter_listener_failed",
                channel_id=adapter.channel_id,
                error=str(exc),
            )
            await self.publish_adapter_status(adapter.channel_id, "error", str(exc))

    async def publish_inbound_message(self, message: Any) -> None:
        payload = MessageInboundPayload(message=message)
        event = self._publisher.create_event(
            event_type=ChannelEventTypes.MESSAGE_INBOUND,
            payload=payload.model_dump(mode="json"),
        )
        if not await self._publisher.publish_channel_event_via_outbox(event):
            logger.error("publish_inbound_failed")

    async def publish_adapter_status(
        self,
        channel_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        payload = AdapterStatusPayload(
            channel_id=channel_id,
            status=status,
            error_message=error_message,
        )
        event = self._publisher.create_event(
            event_type=ChannelEventTypes.ADAPTER_STATUS,
            payload=payload.model_dump(mode="json"),
        )
        if not await self._publisher.publish_channel_event_via_outbox(event):
            logger.error("publish_status_failed")
