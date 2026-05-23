"""Application facade for the Coordinator service shell."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.core import unknown_action_error
from shared.schemas.event import Event

from .event_use_cases import CoordinatorEventUseCase, CoordinatorThinkerPort
from .health_ports import CoordinatorHealthStore
from .health_use_cases import CoordinatorHealthUseCase
from .outbox_delivery_use_cases import CoordinatorOutboxDeliveryUseCase
from .outbox_ports import CoordinatorEventOutboxStore
from .state_ports import CoordinatorStateStorePort
from .unit_of_work_ports import CoordinatorUnitOfWorkFactory

StandardRequestHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class CoordinatorApplicationFacade:
    """Coordinate Coordinator application use cases behind the runtime boundary."""

    def __init__(
        self,
        *,
        standard_request_handler: StandardRequestHandler,
        scratchpad_provider: Callable[[], Any],
        state_store_provider: Callable[[], CoordinatorStateStorePort],
        thinker_provider: Callable[[], CoordinatorThinkerPort],
        llm_gateway_provider: Callable[[], Any],
        database_enabled: bool,
        health_store_provider: Callable[[], CoordinatorHealthStore | None],
        outbox_store_provider: Callable[[], CoordinatorEventOutboxStore | None],
        event_bus: Any,
        event_publisher: Any,
        uow_factory_provider: Callable[[], CoordinatorUnitOfWorkFactory | None] | None = None,
    ) -> None:
        self._standard_request_handler = standard_request_handler
        self._scratchpad_provider = scratchpad_provider
        self._state_store_provider = state_store_provider
        self._thinker_provider = thinker_provider
        self._llm_gateway_provider = llm_gateway_provider
        self._database_enabled = database_enabled
        self._health_store_provider = health_store_provider
        self._outbox_store_provider = outbox_store_provider
        self._event_bus = event_bus
        self._event_publisher = event_publisher
        self._uow_factory_provider = uow_factory_provider

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> CoordinatorEventUseCase:
        uow_factory = (
            self._uow_factory_provider()
            if self._uow_factory_provider is not None
            else None
        )
        return CoordinatorEventUseCase(
            scratchpad=self._scratchpad_provider(),
            state_store=self._state_store_provider(),
            thinker=self._thinker_provider(),
            uow_factory=uow_factory,
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        result = await self._standard_request_handler(request)
        if result is not None:
            return result
        return unknown_action_error(action=request.get("action"))

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> CoordinatorHealthUseCase:
        return CoordinatorHealthUseCase(
            scratchpad=self._scratchpad_provider(),
            state_store=self._state_store_provider(),
            llm_gateway=self._llm_gateway_provider(),
            database_enabled=self._database_enabled,
            health_store=self._health_store_provider(),
        )

    async def publish_pending_coordinator_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> CoordinatorOutboxDeliveryUseCase:
        return CoordinatorOutboxDeliveryUseCase(
            outbox_store=self._require_outbox_store(),
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )

    def _require_outbox_store(self) -> CoordinatorEventOutboxStore:
        outbox_store = self._outbox_store_provider()
        if outbox_store is None:
            raise RuntimeError("coordinator_outbox_store_not_started")
        return outbox_store
