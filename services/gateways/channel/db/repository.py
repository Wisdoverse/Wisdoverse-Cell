"""Repository layer for the channel gateway."""

import inspect

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..core.outbox_lifecycle import (
    ChannelGatewayOutboxLifecycle,
    ChannelGatewayOutboxStatus,
)
from ..models.event_outbox import ChannelGatewayEventOutbox


class ChannelGatewayEventOutboxRepository:
    """Channel gateway integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> ChannelGatewayEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        lifecycle = ChannelGatewayOutboxLifecycle.stage(event.event_id)
        row = ChannelGatewayEventOutbox(
            event_id=event.event_id,
            event_type=event.event_type,
            source_agent=event.source_agent,
            payload=payload["payload"],
            schema_version=event.schema_version,
            trace_id=payload["metadata"].get("trace_id"),
            correlation_id=payload["metadata"].get("correlation_id"),
            retry_count=payload["metadata"].get("retry_count", 0),
            status=lifecycle.status.value,
            attempts=lifecycle.attempts,
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
            .where(
                ChannelGatewayEventOutbox.status == ChannelGatewayOutboxStatus.PENDING.value
            )
            .order_by(
                ChannelGatewayEventOutbox.created_at,
                ChannelGatewayEventOutbox.event_id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        row = await self._get_outbox_row(event_id)
        if row is None:
            return
        lifecycle = ChannelGatewayOutboxLifecycle.from_record(row).mark_published()
        await self.session.execute(
            update(ChannelGatewayEventOutbox)
            .where(ChannelGatewayEventOutbox.event_id == event_id)
            .where(
                ChannelGatewayEventOutbox.status == ChannelGatewayOutboxStatus.PENDING.value
            )
            .values(**lifecycle.to_update_values())
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        row = await self._get_outbox_row(event_id)
        if row is None:
            return
        lifecycle = ChannelGatewayOutboxLifecycle.from_record(row).record_failure(error)
        await self.session.execute(
            update(ChannelGatewayEventOutbox)
            .where(ChannelGatewayEventOutbox.event_id == event_id)
            .where(
                ChannelGatewayEventOutbox.status == ChannelGatewayOutboxStatus.PENDING.value
            )
            .values(**lifecycle.to_update_values())
        )

    async def _get_outbox_row(self, event_id: str) -> ChannelGatewayEventOutbox | None:
        result = await self.session.execute(
            select(ChannelGatewayEventOutbox).where(ChannelGatewayEventOutbox.event_id == event_id)
        )
        return result.scalar_one_or_none()
