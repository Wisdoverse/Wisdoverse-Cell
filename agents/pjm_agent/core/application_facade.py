"""Application facade for the PJM Agent service shell."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from .alert_ports import PJMAlertLogStore
from .decomposition_ports import PJMDecompositionStore
from .event_use_cases import PJMEventUseCase, PJMMetricsPort
from .health_ports import PJMHealthStore
from .health_use_cases import PJMHealthUseCase
from .request_use_cases import PJMRequestUseCase

logger = get_logger("pjm_agent.application")

STALE_APPROVAL_HOURS = 24


class PJMApplicationFacade:
    """Coordinate PJM application use cases behind the runtime agent boundary."""

    def __init__(
        self,
        *,
        standard_request_handler: Any,
        config_provider: Callable[[], Any],
        alert_provider: Callable[[], Any],
        push_provider: Callable[[], Any],
        report_provider: Callable[[], Any],
        decomposition_provider: Callable[[], Any],
        decomposition_store_provider: Callable[[], PJMDecompositionStore],
        alert_log_store: PJMAlertLogStore,
        health_store: PJMHealthStore,
        event_factory: Any,
        metrics: PJMMetricsPort,
    ) -> None:
        self._standard_request_handler = standard_request_handler
        self._config_provider = config_provider
        self._alert_provider = alert_provider
        self._push_provider = push_provider
        self._report_provider = report_provider
        self._decomposition_provider = decomposition_provider
        self._decomposition_store_provider = decomposition_store_provider
        self._alert_log_store = alert_log_store
        self._health_store = health_store
        self._event_factory = event_factory
        self._metrics = metrics

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> PJMEventUseCase:
        return PJMEventUseCase(
            agent_id=self._event_factory.agent_id,
            config=self._config_provider(),
            alert=self._alert_provider(),
            push=self._push_provider(),
            alert_log_store=self._alert_log_store,
            decomposition=self._decomposition_provider(),
            event_factory=self._event_factory,
            metrics=self._metrics,
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        standard_response = await self._standard_request_handler(request)
        if standard_response is not None:
            return standard_response
        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> PJMRequestUseCase:
        return PJMRequestUseCase(
            config=self._config_provider(),
            alert=self._alert_provider(),
            push=self._push_provider(),
            report=self._report_provider(),
            decomposition=self._decomposition_provider(),
            decomposition_store=self._decomposition_store_provider(),
        )

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> PJMHealthUseCase:
        return PJMHealthUseCase(
            health_store=self._health_store,
            config=self._config_provider(),
        )

    async def publish_pending_pjm_events(self, limit: int = 100) -> dict[str, int]:
        return await self._require_decomposition().publish_pending_pjm_events(limit=limit)

    async def publish_event_via_outbox(
        self,
        event: Event,
        *,
        wp_id: int | None = None,
    ) -> None:
        await self._require_decomposition().publish_event_via_outbox(event, wp_id=wp_id)

    async def check_approval_timeouts(self) -> None:
        pending = await self._decomposition_store_provider().list_stale_pending(
            older_than_hours=STALE_APPROVAL_HOURS
        )
        now = datetime.now(UTC)
        for record in pending:
            created_at = getattr(record, "created_at", None)
            if not created_at:
                continue
            age = now - created_at
            if age <= timedelta(hours=STALE_APPROVAL_HOURS):
                continue
            logger.warning(
                "approval_timeout",
                record_id=record.id,
                age_hours=age.total_seconds() / 3600,
            )
            timeout_event = self._event_factory.create_event(
                EventTypes.PM_APPROVAL_TIMEOUT,
                {
                    "record_id": str(record.id),
                    "age_hours": round(age.total_seconds() / 3600, 1),
                },
            )
            try:
                await self.publish_event_via_outbox(timeout_event)
            except Exception as exc:
                logger.error("approval_timeout_notify_failed", error=str(exc))

    async def approve_decomposition(self, wp_id: int, approved_by: str) -> dict | None:
        return await self._require_decomposition().approve_decomposition(wp_id, approved_by)

    async def reject_decomposition(
        self, wp_id: int, rejected_by: str, reason: str = ""
    ) -> dict | None:
        return await self._require_decomposition().reject_decomposition(
            wp_id,
            rejected_by,
            reason=reason,
        )

    def _require_decomposition(self) -> Any:
        decomposition = self._decomposition_provider()
        if decomposition is None:
            raise RuntimeError("decomposition_orchestrator_not_started")
        return decomposition
