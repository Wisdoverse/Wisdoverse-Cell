"""Application use cases for Requirement outbox delivery."""
from __future__ import annotations

from typing import Any, Protocol

from shared.observability.outbox import record_outbox_pending_age
from shared.schemas.event import Event, EventMetadata
from shared.utils.logger import get_logger

from .outbox_ports import RequirementEventOutboxStore

logger = get_logger("requirement-manager.outbox_delivery")


class RequirementOutboxEventPublisherPort(Protocol):
    """Event publisher boundary for Requirement outbox delivery."""

    async def publish(self, event: Event) -> bool:
        """Publish one event and return whether it was accepted."""


class RequirementOutboxDeliveryUseCase:
    """Deliver Requirement integration events through the durable outbox."""

    def __init__(
        self,
        *,
        outbox_store: RequirementEventOutboxStore,
        event_publisher: RequirementOutboxEventPublisherPort,
    ) -> None:
        self._outbox_store = outbox_store
        self._event_publisher = event_publisher

    async def publish_pending_events(self, limit: int = 100) -> dict[str, int]:
        rows = await self._outbox_store.list_pending(limit=limit)
        record_outbox_pending_age("requirement-manager", rows)

        published = 0
        failed = 0
        for row in rows:
            event = self.event_from_outbox(row)
            if await self.publish_staged_event(event, requirement_id=None):
                published += 1
            else:
                failed += 1

        logger.info(
            "requirement_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        await self._outbox_store.add(event)
        await self.publish_staged_event(event, requirement_id=None)
        return True

    def event_from_outbox(self, row: Any) -> Event:
        """Rebuild an immutable Event from a Requirement outbox row."""
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
        requirement_id: str | None,
    ) -> bool:
        """Publish one event already persisted in the Requirement outbox."""
        try:
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self.mark_event_published(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement_id,
            )
            return True
        except Exception as exc:
            await self.mark_event_failed(event, exc)
            logger.error(
                "event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement_id,
                error=str(exc),
            )
            return False

    async def mark_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published Requirement outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "requirement_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def mark_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a Requirement outbox publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "requirement_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )
