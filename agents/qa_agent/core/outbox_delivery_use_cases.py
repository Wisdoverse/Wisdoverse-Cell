"""Application use cases for QA outbox delivery."""

from __future__ import annotations

from typing import Any, Protocol

from shared.core.identifiers import AcceptanceRunId
from shared.observability.outbox import record_outbox_pending_age
from shared.schemas.event import Event, EventMetadata
from shared.utils.logger import get_logger

from .outbox_ports import QAEventOutboxStore

logger = get_logger("qa_agent.outbox_delivery")


class QAOutboxEventPublisherPort(Protocol):
    """Event publisher boundary for QA outbox delivery."""

    async def publish(self, event: Event) -> bool:
        """Publish one event and return whether it was accepted."""


class QAOutboxDeliveryUseCase:
    """Deliver QA integration events through the durable outbox."""

    def __init__(
        self,
        *,
        outbox_store: QAEventOutboxStore,
        event_publisher: QAOutboxEventPublisherPort,
    ) -> None:
        self._outbox_store = outbox_store
        self._event_publisher = event_publisher

    async def publish_pending_events(self, limit: int = 100) -> dict[str, int]:
        rows = await self._outbox_store.list_pending(limit=limit)
        record_outbox_pending_age("qa-agent", rows)

        published = 0
        failed = 0
        for row in rows:
            event = self.event_from_outbox(row)
            if await self.publish_staged_event(event, run_id=None):
                published += 1
            else:
                failed += 1

        logger.info(
            "qa_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        await self._outbox_store.add(event)
        result = await self.publish_staged_events([event], run_id=None)
        return bool(result.get("sent"))

    async def publish_staged_events(
        self,
        events: list[Event],
        *,
        run_id: AcceptanceRunId | None,
    ) -> dict[str, Any]:
        """Publish events already committed to the local QA outbox."""
        if not events:
            return {"sent": False, "reason": "no_events"}

        published = 0
        failed = 0
        for event in events:
            if await self.publish_staged_event(event, run_id=run_id):
                published += 1
            else:
                failed += 1

        return {
            "sent": failed == 0,
            "published": published,
            "failed": failed,
        }

    def event_from_outbox(self, row: Any) -> Event:
        """Rebuild an immutable Event from a QA outbox row."""
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

    async def publish_staged_event(
        self,
        event: Event,
        *,
        run_id: AcceptanceRunId | None,
    ) -> bool:
        """Publish one event already persisted in the QA outbox."""
        try:
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self.mark_event_published(event)
            return True
        except Exception as exc:
            await self.mark_event_failed(event, exc)
            logger.error(
                "qa_event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                run_id=run_id,
                error=str(exc),
            )
            return False

    async def mark_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published QA outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "qa_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def mark_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a QA outbox publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "qa_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )
