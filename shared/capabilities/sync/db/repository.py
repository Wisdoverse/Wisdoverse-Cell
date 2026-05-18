"""
SyncModule repository layer.
"""
import inspect
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..models.sync import SubtaskMapping, SyncEventOutbox, SyncLock, SyncLog, SyncMapping


class SyncMappingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_op_id(self, op_id: int) -> Optional[SyncMapping]:
        result = await self.session.execute(
            select(SyncMapping).where(SyncMapping.op_work_package_id == op_id)
        )
        return result.scalar_one_or_none()

    async def get_by_record_id(self, record_id: str) -> Optional[SyncMapping]:
        result = await self.session.execute(
            select(SyncMapping).where(SyncMapping.feishu_record_id == record_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, op_id: int, record_id: str, project_id: int | None = None, title: str | None = None
    ) -> SyncMapping:
        mapping = await self.get_by_op_id(op_id)
        now = datetime.now(UTC)
        if mapping:
            mapping.feishu_record_id = record_id
            if project_id is not None:
                mapping.op_project_id = project_id
            if title is not None:
                mapping.title = title
            mapping.updated_at = now
        else:
            mapping = SyncMapping(
                op_work_package_id=op_id,
                feishu_record_id=record_id,
                op_project_id=project_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
            self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def list_all(self) -> list[SyncMapping]:
        result = await self.session.execute(select(SyncMapping))
        return list(result.scalars().all())


class SubtaskMappingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_record_id(self, record_id: str) -> Optional[SubtaskMapping]:
        result = await self.session.execute(
            select(SubtaskMapping).where(SubtaskMapping.feishu_record_id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_by_parent(self, parent_op_id: int) -> list[SubtaskMapping]:
        result = await self.session.execute(
            select(SubtaskMapping).where(SubtaskMapping.parent_op_id == parent_op_id)
        )
        return list(result.scalars().all())

    async def upsert(
        self, parent_op_id: int, record_id: str, name: str | None = None, status: str | None = None
    ) -> SubtaskMapping:
        mapping = await self.get_by_record_id(record_id)
        now = datetime.now(UTC)
        if mapping:
            if name is not None:
                mapping.subtask_name = name
            if status is not None:
                mapping.subtask_status = status
            mapping.updated_at = now
        else:
            mapping = SubtaskMapping(
                parent_op_id=parent_op_id,
                feishu_record_id=record_id,
                subtask_name=name,
                subtask_status=status,
            )
            self.session.add(mapping)
        await self.session.flush()
        return mapping


class SyncLockRepository:
    """Distributed lock repository using PostgreSQL row locks."""

    LOCK_TIMEOUT_MINUTES = 10

    def __init__(self, session: AsyncSession):
        self.session = session

    async def acquire(self, lock_name: str, locked_by: str) -> bool:
        """Try to acquire a lock and release it automatically after timeout."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.LOCK_TIMEOUT_MINUTES)

        lock = await self.session.execute(
            select(SyncLock).where(SyncLock.lock_name == lock_name).with_for_update()
        )
        lock_row = lock.scalar_one_or_none()

        if lock_row is None:
            self.session.add(SyncLock(
                lock_name=lock_name, locked_by=locked_by,
                locked_at=now, expires_at=expires_at, is_locked=True,
            ))
            await self.session.flush()
            return True

        # Expired locks can be acquired.
        if lock_row.is_locked and lock_row.expires_at and lock_row.expires_at < now:
            lock_row.locked_by = locked_by
            lock_row.locked_at = now
            lock_row.expires_at = expires_at
            lock_row.is_locked = True
            await self.session.flush()
            return True

        if not lock_row.is_locked:
            lock_row.locked_by = locked_by
            lock_row.locked_at = now
            lock_row.expires_at = expires_at
            lock_row.is_locked = True
            await self.session.flush()
            return True

        return False

    async def release(self, lock_name: str) -> None:
        await self.session.execute(
            update(SyncLock)
            .where(SyncLock.lock_name == lock_name)
            .values(is_locked=False, locked_by=None)
        )
        await self.session.flush()


class SyncLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, sync_type: str, status: str) -> SyncLog:
        log = SyncLog(sync_type=sync_type, status=status)
        self.session.add(log)
        await self.session.flush()
        return log

    async def complete(self, log_id: int, records_processed: int, error: str | None = None):
        result = await self.session.execute(
            select(SyncLog).where(SyncLog.id == log_id)
        )
        log = result.scalar_one()
        log.status = "failed" if error else "completed"
        log.records_processed = records_processed
        log.error_message = error
        log.completed_at = datetime.now(UTC)
        await self.session.flush()


class SyncEventOutboxRepository:
    """Sync integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> SyncEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = SyncEventOutbox(
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
        result = self.session.flush()
        if inspect.isawaitable(result):
            await result
        return row

    async def list_pending(self, limit: int = 100) -> list[SyncEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(SyncEventOutbox)
            .where(SyncEventOutbox.status == "pending")
            .order_by(SyncEventOutbox.created_at, SyncEventOutbox.event_id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(SyncEventOutbox)
            .where(SyncEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=SyncEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(SyncEventOutbox)
            .where(SyncEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=SyncEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )
