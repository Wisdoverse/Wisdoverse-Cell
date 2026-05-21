from unittest.mock import AsyncMock

import pytest

from agents.pjm_agent.db.decomposition_store import SqlAlchemyPJMDecompositionStore


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DbManager:
    def __init__(self, session):
        self._session = session

    def async_session(self):
        return _SessionContext(self._session)


@pytest.mark.asyncio
async def test_pjm_decomposition_transaction_commits_explicitly() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    store = SqlAlchemyPJMDecompositionStore(_DbManager(session))

    async with store.transaction() as transaction:
        assert transaction.completed is False
        await transaction.commit()

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_pjm_decomposition_transaction_rolls_back_on_uncommitted_exit() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    store = SqlAlchemyPJMDecompositionStore(_DbManager(session))

    async with store.transaction() as transaction:
        assert transaction.completed is False

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_pjm_decomposition_transaction_rolls_back_on_exception() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    store = SqlAlchemyPJMDecompositionStore(_DbManager(session))

    with pytest.raises(RuntimeError, match="boom"):
        async with store.transaction():
            raise RuntimeError("boom")

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
