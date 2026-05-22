"""Application facade for the Evolution capability service shell."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.schemas.event import Event

from .event_use_cases import EvolutionEventUseCase
from .health_ports import EvolutionHealthStore
from .health_use_cases import EvolutionHealthUseCase
from .outbox_delivery_use_cases import EvolutionOutboxDeliveryUseCase
from .outbox_ports import EvolutionEventOutboxStore
from .request_use_cases import EvolutionAnalyzerPort, EvolutionRequestUseCase
from .seed_bootstrap_use_cases import EvolutionSeedBootstrapUseCase
from .seed_ports import EvolutionSkillSeedStore

StandardRequestHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class EvolutionApplicationFacade:
    """Coordinate Evolution application use cases behind the runtime boundary."""

    def __init__(
        self,
        *,
        standard_request_handler: StandardRequestHandler,
        analyzer_provider: Callable[[], EvolutionAnalyzerPort],
        attach_proposal_approval: Any,
        event_factory: Any,
        approval_service_provider: Callable[[], Any],
        approval_gateway_provider: Callable[[], Any],
        collaboration_enabled_provider: Callable[[], bool],
        health_store_provider: Callable[[], EvolutionHealthStore],
        event_bus: Any,
        llm_gateway_provider: Callable[[], Any],
        seed_store_provider: Callable[[], EvolutionSkillSeedStore],
        outbox_store_provider: Callable[[], EvolutionEventOutboxStore],
        event_publisher: Any,
    ) -> None:
        self._standard_request_handler = standard_request_handler
        self._analyzer_provider = analyzer_provider
        self._attach_proposal_approval = attach_proposal_approval
        self._event_factory = event_factory
        self._approval_service_provider = approval_service_provider
        self._approval_gateway_provider = approval_gateway_provider
        self._collaboration_enabled_provider = collaboration_enabled_provider
        self._health_store_provider = health_store_provider
        self._event_bus = event_bus
        self._llm_gateway_provider = llm_gateway_provider
        self._seed_store_provider = seed_store_provider
        self._outbox_store_provider = outbox_store_provider
        self._event_publisher = event_publisher

    async def bootstrap_seeds(self) -> int:
        return await self._seed_bootstrap_use_case().bootstrap()

    def _seed_bootstrap_use_case(self) -> EvolutionSeedBootstrapUseCase:
        return EvolutionSeedBootstrapUseCase(seed_store=self._seed_store_provider())

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> EvolutionEventUseCase:
        return EvolutionEventUseCase(
            analyzer=self._analyzer_provider(),
            attach_proposal_approval=self._attach_proposal_approval,
            event_factory=self._event_factory,
            approval_service=self._approval_service_provider(),
            approval_gateway=self._approval_gateway_provider(),
            collaboration_enabled=self._collaboration_enabled_provider(),
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        standard_response = await self._standard_request_handler(request)
        if standard_response is not None:
            return standard_response
        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> EvolutionRequestUseCase:
        return EvolutionRequestUseCase(
            analyzer=self._analyzer_provider(),
            attach_proposal_approval=self._attach_proposal_approval,
        )

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> EvolutionHealthUseCase:
        return EvolutionHealthUseCase(
            health_store=self._health_store_provider(),
            event_bus=self._event_bus,
            llm_gateway=self._llm_gateway_provider(),
            approval_service=self._approval_service_provider(),
            collaboration_enabled=self._collaboration_enabled_provider(),
            approval_gateway=self._approval_gateway_provider(),
        )

    async def publish_pending_evolution_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> EvolutionOutboxDeliveryUseCase:
        return EvolutionOutboxDeliveryUseCase(
            outbox_store=self._outbox_store_provider(),
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )
