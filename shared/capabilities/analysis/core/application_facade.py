"""Application facade for the Analysis capability service shell."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.schemas.event import Event

from .event_use_cases import AnalysisEventUseCase, AnalysisMetricsPort
from .health_ports import AnalysisHealthStore
from .health_use_cases import AnalysisHealthUseCase
from .outbox_delivery_use_cases import AnalysisOutboxDeliveryUseCase
from .outbox_ports import AnalysisEventOutboxStore
from .request_use_cases import AnalysisRequestUseCase

StandardRequestHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
ComponentProvider = Callable[[], Any]


class AnalysisApplicationFacade:
    """Coordinate Analysis application use cases behind the runtime boundary."""

    def __init__(
        self,
        *,
        standard_request_handler: StandardRequestHandler,
        daily_provider: ComponentProvider,
        weekly_provider: ComponentProvider,
        milestone_provider: ComponentProvider,
        quality_provider: ComponentProvider,
        event_factory: Any,
        metrics: AnalysisMetricsPort,
        health_store_provider: Callable[[], AnalysisHealthStore],
        event_bus: Any,
        outbox_store_provider: Callable[[], AnalysisEventOutboxStore],
        event_publisher: Any,
    ) -> None:
        self._standard_request_handler = standard_request_handler
        self._daily_provider = daily_provider
        self._weekly_provider = weekly_provider
        self._milestone_provider = milestone_provider
        self._quality_provider = quality_provider
        self._event_factory = event_factory
        self._metrics = metrics
        self._health_store_provider = health_store_provider
        self._event_bus = event_bus
        self._outbox_store_provider = outbox_store_provider
        self._event_publisher = event_publisher

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> AnalysisEventUseCase:
        return AnalysisEventUseCase(
            daily=self._daily_provider(),
            weekly=self._weekly_provider(),
            milestone=self._milestone_provider(),
            quality=self._quality_provider(),
            event_factory=self._event_factory,
            metrics=self._metrics,
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        standard_response = await self._standard_request_handler(request)
        if standard_response is not None:
            return standard_response
        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> AnalysisRequestUseCase:
        return AnalysisRequestUseCase(
            daily=self._daily_provider(),
            weekly=self._weekly_provider(),
            milestone=self._milestone_provider(),
        )

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> AnalysisHealthUseCase:
        return AnalysisHealthUseCase(
            health_store=self._health_store_provider(),
            event_bus=self._event_bus,
        )

    async def publish_pending_analysis_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> AnalysisOutboxDeliveryUseCase:
        return AnalysisOutboxDeliveryUseCase(
            outbox_store=self._outbox_store_provider(),
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )
