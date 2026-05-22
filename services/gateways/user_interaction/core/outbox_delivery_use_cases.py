"""Application use cases for user-interaction outbox delivery."""
from __future__ import annotations

from typing import Any, Protocol

from shared.observability.outbox import record_outbox_pending_age
from shared.schemas.event import Event, EventMetadata
from shared.utils.logger import get_logger

from .event_ports import UserInteractionEventOutboxStore

logger = get_logger("chat_agent.outbox_delivery")


class UserInteractionOutboxEventBusPort(Protocol):
    """Event bus lifecycle boundary required before publishing."""

    async def connect(self) -> None:
        """Ensure the EventBus transport is ready."""


class UserInteractionOutboxEventPublisherPort(Protocol):
    """Event publisher boundary for user-interaction outbox delivery."""

    async def publish(self, event: Event) -> bool:
        """Publish one event and return whether it was accepted."""


class UserInteractionOutboxDeliveryUseCase:
    """Deliver user-interaction integration events through the durable outbox."""

    def __init__(
        self,
        *,
        outbox_store: UserInteractionEventOutboxStore,
        event_bus: UserInteractionOutboxEventBusPort,
        event_publisher: UserInteractionOutboxEventPublisherPort,
    ) -> None:
        self._outbox_store = outbox_store
        self._event_bus = event_bus
        self._event_publisher = event_publisher

    async def publish_pending_events(self, limit: int = 100) -> dict[str, int]:
        rows = await self._outbox_store.list_pending(limit=limit)
        record_outbox_pending_age("chat-agent", rows)

        published = 0
        failed = 0
        for row in rows:
            event = self.event_from_outbox(row)
            if await self.publish_staged_event(event):
                published += 1
            else:
                failed += 1

        logger.info(
            "chat_agent_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        await self._outbox_store.add(event)
        return await self.publish_staged_event(event)

    def event_from_outbox(self, row: Any) -> Event:
        """Rebuild an immutable Event from a gateway outbox row."""
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
        """Publish an event already persisted in the gateway outbox."""
        try:
            await self._event_bus.connect()
            published = await self._event_publisher.publish(event)
            if not published:
                raise RuntimeError("event_bus_publish_returned_false")
            await self.mark_event_published(event)
            return True
        except Exception as exc:
            await self.mark_event_failed(event, exc)
            logger.warning(
                "chat_agent_outbox_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False

    async def mark_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published gateway outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "chat_agent_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def mark_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a gateway outbox publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "chat_agent_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )
