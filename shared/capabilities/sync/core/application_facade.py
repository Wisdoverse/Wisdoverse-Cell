"""Application facade for the Sync Capability service shell."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.schemas.event import Event

from .event_use_cases import SyncEventUseCase
from .health_ports import SyncHealthStore
from .health_use_cases import SyncHealthUseCase
from .outbox_delivery_use_cases import SyncOutboxDeliveryUseCase
from .request_use_cases import SyncRequestUseCase
from .scope_execution_use_cases import SyncScopeExecutionUseCase
from .sync_ports import SyncEventOutboxStore

SyncScopeRunner = Callable[[], Awaitable[dict[str, Any]]]


class SyncApplicationFacade:
    """Coordinate Sync application use cases behind the runtime boundary."""

    def __init__(
        self,
        *,
        agent_id: str,
        standard_request_handler: Any,
        sync_engine_provider: Callable[[], Any],
        health_store: SyncHealthStore,
        outbox_store_provider: Callable[[], SyncEventOutboxStore],
        event_factory: Any,
        event_publisher: Any,
        metrics: Any,
    ) -> None:
        self._agent_id = agent_id
        self._standard_request_handler = standard_request_handler
        self._sync_engine_provider = sync_engine_provider
        self._health_store = health_store
        self._outbox_store_provider = outbox_store_provider
        self._event_factory = event_factory
        self._event_publisher = event_publisher
        self._metrics = metrics

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> SyncEventUseCase:
        return SyncEventUseCase(sync_runner=self)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        standard_response = await self._standard_request_handler(request)
        if standard_response is not None:
            return standard_response
        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> SyncRequestUseCase:
        return SyncRequestUseCase(sync_runner=self, agent_id=self._agent_id)

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> SyncHealthUseCase:
        return SyncHealthUseCase(health_store=self._health_store)

    async def trigger_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Run both sync boundaries and publish compatibility sync events."""
        return await self.run_sync_scope(
            scope="full",
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=lambda: self._require_sync_engine().full_sync(trace_id=trace_id),
        )

    async def trigger_openproject_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the OpenProject-to-Bitable projection sync only."""
        return await self.run_sync_scope(
            scope="openproject",
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=lambda: self._require_sync_engine().sync_op_to_feishu(
                trace_id=trace_id
            ),
        )

    async def trigger_feishu_bitable_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the Feishu Bitable-to-OpenProject progress sync only."""
        return await self.run_sync_scope(
            scope="feishu_bitable",
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=lambda: self._require_sync_engine().sync_feishu_to_op(
                trace_id=trace_id
            ),
        )

    async def run_sync_scope(
        self,
        *,
        scope: str,
        triggered_by: str,
        trace_id: str | None,
        runner: SyncScopeRunner,
    ) -> dict[str, Any]:
        return await self._scope_execution_use_case().run_scope(
            scope=scope,
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=runner,
        )

    def _scope_execution_use_case(self) -> SyncScopeExecutionUseCase:
        return SyncScopeExecutionUseCase(
            event_factory=self._event_factory,
            event_publisher=self,
            metrics=self._metrics,
        )

    async def publish_sync_event_via_outbox(self, event: Event) -> None:
        await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    async def publish_pending_sync_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(limit=limit)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        await self.publish_sync_event_via_outbox(event)
        return True

    def _outbox_delivery_use_case(self) -> SyncOutboxDeliveryUseCase:
        return SyncOutboxDeliveryUseCase(
            outbox_store=self._outbox_store_provider(),
            event_publisher=self._event_publisher,
        )

    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return self._event_factory.create_event(event_type, payload, trace_id=trace_id)

    def _require_sync_engine(self) -> Any:
        sync_engine = self._sync_engine_provider()
        if sync_engine is None:
            raise RuntimeError("sync_engine_not_started")
        return sync_engine
