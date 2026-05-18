"""Application use cases for executing Sync scopes."""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

logger = get_logger("sync_module.scope_execution")


SyncScopeRunner = Callable[[], Awaitable[dict[str, Any]]]


class SyncScopeEventFactoryPort(Protocol):
    """Event factory owned by the Sync service shell."""

    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        """Create a Sync event with service identity."""


class SyncScopeEventPublisherPort(Protocol):
    """Durable event publisher boundary for Sync lifecycle events."""

    async def publish_sync_event_via_outbox(self, event: Event) -> None:
        """Stage and publish one Sync lifecycle event."""


class SyncScopeMetricsPort(Protocol):
    """Metrics adapter boundary for Sync scope execution."""

    def record_sync_success(
        self,
        *,
        triggered_by: str,
        scope: str,
        synced_count: int,
        duration_seconds: float,
    ) -> None:
        """Record a successful sync execution."""

    def record_sync_failure(self, *, triggered_by: str) -> None:
        """Record a failed sync execution."""


class SyncScopeExecutionUseCase:
    """Run one Sync scope and publish scoped lifecycle events."""

    def __init__(
        self,
        *,
        event_factory: SyncScopeEventFactoryPort,
        event_publisher: SyncScopeEventPublisherPort,
        metrics: SyncScopeMetricsPort,
    ) -> None:
        self._event_factory = event_factory
        self._event_publisher = event_publisher
        self._metrics = metrics

    async def run_scope(
        self,
        *,
        scope: str,
        triggered_by: str,
        trace_id: str | None,
        runner: SyncScopeRunner,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        start_event = self._event_factory.create_event(
            EventTypes.SYNC_STARTED,
            {"triggered_by": triggered_by, "scope": scope},
            trace_id=trace_id,
        )
        await self._publish_lifecycle_event(start_event)

        try:
            result = await runner()
            synced_count = _synced_count(result)
            errors = _sync_errors(result)
            complete_event = self._event_factory.create_event(
                EventTypes.SYNC_COMPLETED,
                {
                    "synced_count": synced_count,
                    "scope": scope,
                    "errors": errors,
                },
                trace_id=start_event.metadata.trace_id,
            )
            await self._publish_lifecycle_event(complete_event)

            logger.info(
                "sync_completed",
                scope=scope,
                status=result.get("status"),
                synced_count=synced_count,
                error_count=len(errors),
            )
            self._metrics.record_sync_success(
                triggered_by=triggered_by,
                scope=scope,
                synced_count=synced_count,
                duration_seconds=time.perf_counter() - start,
            )
            return result
        except Exception as exc:
            fail_event = self._event_factory.create_event(
                EventTypes.SYNC_FAILED,
                {
                    "error": str(exc),
                    "error_code": "sync_scope_failed",
                    "scope": scope,
                },
                trace_id=start_event.metadata.trace_id,
            )
            await self._publish_lifecycle_event(fail_event)
            logger.error("sync_failed", error=str(exc))
            self._metrics.record_sync_failure(triggered_by=triggered_by)
            return {"status": "failed", "error": str(exc)}

    async def _publish_lifecycle_event(self, event: Event) -> None:
        try:
            await self._event_publisher.publish_sync_event_via_outbox(event)
        except Exception as exc:
            logger.error(
                "event_publish_failed",
                event_type=event.event_type,
                error=str(exc),
            )


def _synced_count(result: dict[str, Any]) -> int:
    return result.get("total_processed", result.get("processed", 0))


def _sync_errors(result: dict[str, Any]) -> list[Any]:
    return (
        result.get("op_to_feishu", {}).get("errors", [])
        + result.get("feishu_to_op", {}).get("errors", [])
        + result.get("errors", [])
    )
