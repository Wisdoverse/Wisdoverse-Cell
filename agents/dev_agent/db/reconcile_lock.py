"""SQLAlchemy-backed reconciliation lock adapter."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyDevReconcileLock:
    """PostgreSQL advisory lock for single-instance Dev reconciliation."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def try_acquire(self) -> bool:
        result = await self._session.execute(
            text("SELECT pg_try_advisory_lock(hashtext('dev_agent_reconcile'))")
        )
        return bool(result.scalar())

    async def release(self) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_unlock(hashtext('dev_agent_reconcile'))")
        )
