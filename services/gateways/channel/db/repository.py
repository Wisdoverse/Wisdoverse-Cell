"""Repository layer for the channel gateway."""

import inspect
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..models.event_outbox import ChannelGatewayEventOutbox


class ChannelGatewayEventOutboxRepository:
    """Channel gateway integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> ChannelGatewayEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = ChannelGatewayEventOutbox(
            event_id=event.event_id,
            event_type=event.event_type,
            source_agent=event.source_agent,
            payload=payload["payload"],
            schema_version=event.schema_version,
            trace_id=payload["metadata"].get("trace_id"),
            correlation_id=payload["metadata"].get("correlation_id"),
            retry_count=payload["metadata"].get("retry_count", 0),
            status="pending",
            attempts=0,
        )
        add_result = self.session.add(row)
        if inspect.isawaitable(add_result):
            await add_result
        flush_result = self.session.flush()
        if inspect.isawaitable(flush_result):
            await flush_result
        return row

    async def list_pending(self, limit: int = 100) -> list[ChannelGatewayEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(ChannelGatewayEventOutbox)
            .where(ChannelGatewayEventOutbox.status == "pending")
            .order_by(
                ChannelGatewayEventOutbox.created_at,
                ChannelGatewayEventOutbox.event_id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(ChannelGatewayEventOutbox)
            .where(ChannelGatewayEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=ChannelGatewayEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(ChannelGatewayEventOutbox)
            .where(ChannelGatewayEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=ChannelGatewayEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )
