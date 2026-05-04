"""Shared lock helper for sync capability engines."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from shared.utils.logger import get_logger

from ..db.database import DatabaseManager
from ..db.repository import SyncLockRepository

logger = get_logger("sync_capability.locking")


@asynccontextmanager
async def acquire_sync_lock(
    db_manager: DatabaseManager,
    lock_name: str,
    *,
    locked_by: str = "sync-agent",
) -> AsyncIterator[bool]:
    """Acquire and release a sync lock around one bounded sync operation."""
    acquired = False
    try:
        async with db_manager.session() as session:
            lock_repo = SyncLockRepository(session)
            acquired = await lock_repo.acquire(lock_name, locked_by)
            if not acquired:
                logger.warning("sync_lock_held", lock=lock_name)
            yield acquired
    finally:
        if acquired:
            try:
                async with db_manager.session() as release_session:
                    release_repo = SyncLockRepository(release_session)
                    await release_repo.release(lock_name)
            except Exception as release_err:
                logger.error(
                    "sync_lock_release_failed",
                    lock=lock_name,
                    error=str(release_err),
                    error_type=type(release_err).__name__,
                )
