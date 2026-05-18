"""Application use cases for Analysis outbox delivery."""
from __future__ import annotations

from typing import Any, Protocol

from shared.schemas.event import Event, EventMetadata
from shared.utils.logger import get_logger

from .outbox_ports import AnalysisEventOutboxStore

logger = get_logger("analysis_module.outbox_delivery")


class AnalysisOutboxEventBusPort(Protocol):
    """Event bus connection boundary required before publish."""

    async def connect(self) -> None:
        """Ensure the event bus connection is ready."""


class AnalysisOutboxEventPublisherPort(Protocol):
    """Event publisher boundary for outbox delivery."""

    async def publish(self, event: Event) -> bool:
        """Publish one event and return whether it was accepted."""


class AnalysisOutboxDeliveryUseCase:
    """Deliver Analysis integration events through the durable outbox."""

    def __init__(
        self,
        *,
        outbox_store: AnalysisEventOutboxStore,
        event_bus: AnalysisOutboxEventBusPort,
        event_publisher: AnalysisOutboxEventPublisherPort,
    ) -> None:
        self._outbox_store = outbox_store
        self._event_bus = event_bus
        self._event_publisher = event_publisher

    async def publish_pending_events(self, limit: int = 100) -> dict[str, int]:
        rows = await self._outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self.event_from_outbox(row)
            if await self.publish_staged_event(event):
                published += 1
            else:
                failed += 1

        logger.info(
            "analysis_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        await self._outbox_store.add(event)
        return await self.publish_staged_event(event)

    def event_from_outbox(self, row: Any) -> Event:
        """Rebuild an immutable Event from an Analysis outbox row."""
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

    async def publish_staged_event(self, event: Event) -> bool:
        """Publish one event already persisted in the Analysis outbox."""
        try:
            await self._event_bus.connect()
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self.mark_event_published(event)
            return True
        except Exception as exc:
            await self.mark_event_failed(event, exc)
            logger.error(
                "analysis_outbox_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False

    async def mark_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published Analysis outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "analysis_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def mark_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an Analysis outbox publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "analysis_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )
