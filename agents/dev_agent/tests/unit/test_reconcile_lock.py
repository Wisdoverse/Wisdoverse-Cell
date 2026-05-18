from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.dev_agent.db.reconcile_lock import SqlAlchemyDevReconcileLock


@pytest.mark.asyncio
async def test_reconcile_lock_acquires_postgres_advisory_lock() -> None:
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = True
    session = AsyncMock()
    session.execute = AsyncMock(return_value=scalar_result)

    acquired = await SqlAlchemyDevReconcileLock(session).try_acquire()

    assert acquired is True
    statement = str(session.execute.await_args.args[0])
    assert "pg_try_advisory_lock" in statement
    assert "dev_agent_reconcile" in statement


@pytest.mark.asyncio
async def test_reconcile_lock_releases_postgres_advisory_lock() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()

    await SqlAlchemyDevReconcileLock(session).release()

    statement = str(session.execute.await_args.args[0])
    assert "pg_advisory_unlock" in statement
    assert "dev_agent_reconcile" in statement
