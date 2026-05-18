"""SQLAlchemy adapters for sync core persistence ports."""

import inspect
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.sync_ports import (
    FeishuBitableSyncOperation,
    FeishuBitableSyncStore,
    OpenProjectSyncOperation,
    OpenProjectSyncStore,
    SyncEventOutboxStore,
)
from .database import DatabaseManager
from .repository import (
    SubtaskMappingRepository,
    SyncEventOutboxRepository,
    SyncLockRepository,
    SyncLogRepository,
    SyncMappingRepository,
)


class SqlAlchemySyncLockStore:
    """SQLAlchemy-backed sync lock store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def acquire(self, lock_name: str, locked_by: str) -> bool:
        async with self._db_manager.session() as session:
            repo = SyncLockRepository(session)
            return await repo.acquire(lock_name, locked_by)

    async def release(self, lock_name: str) -> None:
        async with self._db_manager.session() as session:
            repo = SyncLockRepository(session)
            await repo.release(lock_name)


class _SqlAlchemyFeishuBitableSyncOperation(FeishuBitableSyncOperation):
    def __init__(self, session: AsyncSession):
        self._log_repo = SyncLogRepository(session)
        self._subtask_repo = SubtaskMappingRepository(session)

    async def create_log(self, sync_type: str, status: str) -> object:
        return await self._log_repo.create(sync_type, status)

    async def complete_log(
        self,
        log_id: int,
        records_processed: int,
        error: str | None = None,
    ) -> None:
        await self._log_repo.complete(log_id, records_processed, error)

    async def upsert_subtask(
        self,
        *,
        parent_op_id: int,
        record_id: str,
        name: str | None = None,
        status: str | None = None,
    ) -> None:
        await self._subtask_repo.upsert(
            parent_op_id=parent_op_id,
            record_id=record_id,
            name=name,
            status=status,
        )


class SqlAlchemyFeishuBitableSyncStore(FeishuBitableSyncStore):
    """SQLAlchemy-backed unit of work for Feishu-to-OpenProject sync."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    @asynccontextmanager
    async def transaction(
        self,
    ) -> AsyncIterator[FeishuBitableSyncOperation]:
        async with self._db_manager.session() as session:
            yield _SqlAlchemyFeishuBitableSyncOperation(session)


class _SqlAlchemyOpenProjectSyncOperation(OpenProjectSyncOperation):
    def __init__(self, session: AsyncSession):
        self._log_repo = SyncLogRepository(session)
        self._mapping_repo = SyncMappingRepository(session)
        self._outbox_repo = SyncEventOutboxRepository(session)

    async def create_log(self, sync_type: str, status: str) -> object:
        return await self._log_repo.create(sync_type, status)

    async def complete_log(
        self,
        log_id: int,
        records_processed: int,
        error: str | None = None,
    ) -> None:
        await self._log_repo.complete(log_id, records_processed, error)

    async def get_mapping_by_op_id(self, op_id: int) -> object | None:
        return await self._mapping_repo.get_by_op_id(op_id)

    async def upsert_mapping(
        self,
        *,
        op_id: int,
        record_id: str,
        project_id: int | None = None,
        title: str | None = None,
    ) -> None:
        await self._mapping_repo.upsert(
            op_id=op_id,
            record_id=record_id,
            project_id=project_id,
            title=title,
        )

    async def stage_event(self, event: object) -> None:
        await self._outbox_repo.add(event)


class SqlAlchemyOpenProjectSyncStore(OpenProjectSyncStore):
    """SQLAlchemy-backed unit of work for OpenProject-to-Feishu sync."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    @asynccontextmanager
    async def transaction(
        self,
    ) -> AsyncIterator[OpenProjectSyncOperation]:
        async with self._db_manager.session() as session:
            yield _SqlAlchemyOpenProjectSyncOperation(session)

    async def mark_event_published(self, event_id: str) -> None:
        async with self._db_manager.session() as session:
            outbox = SyncEventOutboxRepository(session)
            await outbox.mark_published(event_id)

    async def mark_event_failed(self, event_id: str, error: str) -> None:
        async with self._db_manager.session() as session:
            outbox = SyncEventOutboxRepository(session)
            await outbox.mark_failed(event_id, error)


class SqlAlchemySyncEventOutboxStore(SyncEventOutboxStore):
    """SQLAlchemy-backed Sync event outbox store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def _session_context(self):
        session_context = self._db_manager.session()
        if inspect.isawaitable(session_context):
            session_context = await session_context
        return session_context

    async def add(self, event) -> None:
        async with await self._session_context() as session:
            outbox = SyncEventOutboxRepository(session)
            await outbox.add(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        async with await self._session_context() as session:
            outbox = SyncEventOutboxRepository(session)
            return await outbox.list_pending(limit=limit)

    async def mark_published(self, event_id: str) -> None:
        async with await self._session_context() as session:
            outbox = SyncEventOutboxRepository(session)
            await outbox.mark_published(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        async with await self._session_context() as session:
            outbox = SyncEventOutboxRepository(session)
            await outbox.mark_failed(event_id, error)
