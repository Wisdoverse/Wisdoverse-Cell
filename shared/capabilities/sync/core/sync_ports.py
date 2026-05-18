"""Core ports for sync capability persistence boundaries."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from shared.schemas.event import Event


class SyncLockStore(Protocol):
    """Persistence port for sync distributed locks."""

    async def acquire(self, lock_name: str, locked_by: str) -> bool:
        """Try to acquire a named lock."""

    async def release(self, lock_name: str) -> None:
        """Release a named lock."""


class FeishuBitableSyncOperation(Protocol):
    """Transactional persistence operations for Feishu-to-OpenProject sync."""

    async def create_log(self, sync_type: str, status: str) -> object:
        """Create a sync log row."""

    async def complete_log(
        self,
        log_id: int,
        records_processed: int,
        error: str | None = None,
    ) -> None:
        """Complete a sync log row."""

    async def upsert_subtask(
        self,
        *,
        parent_op_id: int,
        record_id: str,
        name: str | None = None,
        status: str | None = None,
    ) -> None:
        """Upsert a Feishu subtask mapping."""


class FeishuBitableSyncStore(Protocol):
    """Unit-of-work factory for Feishu-to-OpenProject sync persistence."""

    def transaction(
        self,
    ) -> AbstractAsyncContextManager[FeishuBitableSyncOperation]:
        """Open a persistence transaction for one sync run."""


class OpenProjectSyncOperation(Protocol):
    """Transactional persistence operations for OpenProject-to-Feishu sync."""

    async def create_log(self, sync_type: str, status: str) -> object:
        """Create a sync log row."""

    async def complete_log(
        self,
        log_id: int,
        records_processed: int,
        error: str | None = None,
    ) -> None:
        """Complete a sync log row."""

    async def get_mapping_by_op_id(self, op_id: int) -> object | None:
        """Return a mapping for an OpenProject work package id."""

    async def upsert_mapping(
        self,
        *,
        op_id: int,
        record_id: str,
        project_id: int | None = None,
        title: str | None = None,
    ) -> None:
        """Upsert an OpenProject-to-Feishu record mapping."""

    async def stage_event(self, event: object) -> None:
        """Persist an integration event in the sync outbox."""


class OpenProjectSyncStore(Protocol):
    """Unit-of-work factory for OpenProject-to-Feishu sync persistence."""

    def transaction(
        self,
    ) -> AbstractAsyncContextManager[OpenProjectSyncOperation]:
        """Open a persistence transaction for one sync run."""

    async def mark_event_published(self, event_id: str) -> None:
        """Mark a staged sync event as published."""

    async def mark_event_failed(self, event_id: str, error: str) -> None:
        """Record a staged sync event publish failure."""


class SyncEventOutboxStore(Protocol):
    """Persistence port for service-owned Sync event outbox operations."""

    async def add(self, event: Event) -> None:
        """Stage an event before external publish."""

    async def list_pending(self, limit: int = 100) -> list[object]:
        """Return pending outbox rows."""

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure."""
