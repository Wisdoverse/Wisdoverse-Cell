"""SQLAlchemy adapter for identity event outbox persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identity_ports import IdentityEventOutboxStore
from shared.models.identity_event_outbox import IdentityEventOutbox
from shared.schemas.event import Event


class SqlAlchemyIdentityEventOutboxStore(IdentityEventOutboxStore):
    """Session-scoped SQLAlchemy-backed identity event outbox store."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, event: Event) -> None:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = IdentityEventOutbox(
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
            created_at=event.timestamp,
        )
        self._session.add(row)
        await self._session.flush()

    async def list_pending(self, limit: int = 100) -> list[IdentityEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self._session.execute(
            select(IdentityEventOutbox)
            .where(IdentityEventOutbox.status == "pending")
            .order_by(
                IdentityEventOutbox.created_at,
                IdentityEventOutbox.event_id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self._session.execute(
            update(IdentityEventOutbox)
            .where(IdentityEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=IdentityEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self._session.execute(
            update(IdentityEventOutbox)
            .where(IdentityEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=IdentityEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )


__all__ = ["SqlAlchemyIdentityEventOutboxStore"]
