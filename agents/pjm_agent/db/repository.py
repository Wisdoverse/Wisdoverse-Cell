"""Repository - pjm_agent"""

import inspect
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event
from shared.utils.logger import get_logger

from ..models.pm import AlertLog, DecompositionRecord, PJMEventOutbox, PMConfigCache

logger = get_logger("pjm_agent.repository")


class AlertLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, alert_type: str, target: str, message: str, severity: str = "warning"
    ) -> AlertLog:
        log = AlertLog(alert_type=alert_type, target=target, message=message, severity=severity)
        add_result = self.session.add(log)
        if inspect.isawaitable(add_result):
            await add_result
        await self.session.flush()
        return log

    async def get_recent(self, alert_type: str | None = None, limit: int = 20) -> list[AlertLog]:
        query = select(AlertLog).order_by(AlertLog.created_at.desc()).limit(limit)
        if alert_type:
            query = query.where(AlertLog.alert_type == alert_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class PMConfigCacheRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, config_type: str) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(PMConfigCache).where(PMConfigCache.config_type == config_type)
        )
        cache = result.scalar_one_or_none()
        if cache and cache.config_data:
            return json.loads(cache.config_data)
        return None

    async def set(self, config_type: str, data: dict[str, Any]) -> None:
        result = await self.session.execute(
            select(PMConfigCache).where(PMConfigCache.config_type == config_type)
        )
        cache = result.scalar_one_or_none()
        if cache:
            cache.config_data = json.dumps(data, ensure_ascii=False)
            cache.updated_at = datetime.now(UTC)
        else:
            cache = PMConfigCache(
                config_type=config_type, config_data=json.dumps(data, ensure_ascii=False)
            )
            self.session.add(cache)
        await self.session.flush()


class DecompositionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, wp_id: int, project_id: int, decompose_result: dict, assignee_id: int | None = None
    ) -> DecompositionRecord:
        record = DecompositionRecord(
            wp_id=wp_id,
            project_id=project_id,
            assignee_id=assignee_id,
            decompose_result=decompose_result,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_wp_id(self, wp_id: int) -> DecompositionRecord | None:
        result = await self.session.execute(
            select(DecompositionRecord).where(DecompositionRecord.wp_id == wp_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, wp_id: int, status: str, approved_by: str | None = None) -> bool:
        record = await self.get_by_wp_id(wp_id)
        if not record:
            return False
        record.status = status
        record.updated_at = datetime.now(UTC)
        if approved_by:
            record.approved_by = approved_by
            record.approved_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def get_stale_pending(self, older_than_hours: int = 24) -> list[DecompositionRecord]:
        """Return decomposition records with status='pending' older than the given hours."""
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        result = await self.session.execute(
            select(DecompositionRecord)
            .where(DecompositionRecord.status == "pending")
            .where(DecompositionRecord.created_at < cutoff)
        )
        return list(result.scalars().all())

    async def delete_by_wp_id(self, wp_id: int) -> bool:
        record = await self.get_by_wp_id(wp_id)
        if not record:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True


class PJMEventOutboxRepository:
    """PJM integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> PJMEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = PJMEventOutbox(
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
        self.session.add(row)
        result = self.session.flush()
        if inspect.isawaitable(result):
            await result
        return row

    async def list_pending(self, limit: int = 100) -> list[PJMEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(PJMEventOutbox)
            .where(PJMEventOutbox.status == "pending")
            .order_by(PJMEventOutbox.created_at, PJMEventOutbox.event_id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(PJMEventOutbox)
            .where(PJMEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=PJMEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(PJMEventOutbox)
            .where(PJMEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=PJMEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )
