"""Application facade for the channel gateway service shell."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, MutableMapping
from typing import Any

from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .event_use_cases import ChannelGatewayEventUseCase
from .lifecycle_use_cases import ChannelGatewayLifecycleUseCase
from .outbox_delivery_use_cases import ChannelGatewayOutboxDeliveryUseCase
from .outbox_ports import ChannelGatewayEventOutboxStore

logger = get_logger("channel_gateway.application")


class ChannelGatewayApplicationFacade:
    """Coordinate channel gateway use cases behind the runtime boundary."""

    def __init__(
        self,
        *,
        agent_id: str,
        standard_request_handler: Any,
        adapter_registry: Any,
        listener_tasks: MutableMapping[str, asyncio.Task],
        event_factory: Any,
        event_bus: Any,
        event_publisher: Any,
        db_manager_provider: Callable[[], Any],
        outbox_store_provider: Callable[[], ChannelGatewayEventOutboxStore | None],
    ) -> None:
        self._agent_id = agent_id
        self._standard_request_handler = standard_request_handler
        self._adapter_registry = adapter_registry
        self._listener_tasks = listener_tasks
        self._event_factory = event_factory
        self._event_bus = event_bus
        self._event_publisher = event_publisher
        self._db_manager_provider = db_manager_provider
        self._outbox_store_provider = outbox_store_provider

    async def handle_event(self, event: Event) -> list[Event]:
        return await self.channel_event_use_case().handle_event(event)

    def channel_event_use_case(self) -> ChannelGatewayEventUseCase:
        return ChannelGatewayEventUseCase(
            adapter_registry=self._adapter_registry,
            source_agent=self._agent_id,
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        standard_response = await self._standard_request_handler(request)
        if standard_response is not None:
            return standard_response
        return {"status": "ok"}

    async def health_check(self) -> dict[str, bool]:
        adapters = self._adapter_registry.list_all()
        return {
            "event_bus": bool(getattr(self._event_bus, "is_connected", False)),
            "database": self._db_manager_provider() is not None,
            "adapter_registry": self._adapter_registry is not None,
            "adapter_listeners": all(
                adapter.channel_id in self._listener_tasks for adapter in adapters
            ),
        }

    async def connect_adapters(self) -> None:
        await self.channel_lifecycle_use_case().connect_adapters()

    async def connect_adapter(self, adapter: Any) -> None:
        await self.channel_lifecycle_use_case().connect_adapter(adapter)

    async def disconnect_adapters(self) -> None:
        await self.channel_lifecycle_use_case().disconnect_adapters()

    async def run_adapter_listener(self, adapter: Any) -> None:
        await self.channel_lifecycle_use_case().run_adapter_listener(adapter)

    async def publish_inbound_message(self, message: Any) -> None:
        await self.channel_lifecycle_use_case().publish_inbound_message(message)

    async def publish_adapter_status(
        self, channel_id: str, status: str, error_message: str | None = None
    ) -> None:
        await self.channel_lifecycle_use_case().publish_adapter_status(
            channel_id,
            status,
            error_message,
        )

    def channel_lifecycle_use_case(self) -> ChannelGatewayLifecycleUseCase:
        return ChannelGatewayLifecycleUseCase(
            adapter_registry=self._adapter_registry,
            publisher=self._event_factory,
            listener_tasks=self._listener_tasks,
        )

    async def publish_pending_channel_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit
        )

    async def publish_channel_event_via_outbox(self, event: Event) -> bool:
        outbox_store = self._outbox_store_provider()
        if outbox_store is None:
            logger.error(
                "channel_outbox_unavailable",
                event_id=event.event_id,
                event_type=event.event_type,
            )
            return False
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    async def publish_staged_channel_event(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_staged_event(event)

    def _outbox_delivery_use_case(self) -> ChannelGatewayOutboxDeliveryUseCase:
        outbox_store = self._outbox_store_provider()
        if outbox_store is None:
            raise RuntimeError("channel_outbox_store_not_started")
        return ChannelGatewayOutboxDeliveryUseCase(
            outbox_store=outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )
