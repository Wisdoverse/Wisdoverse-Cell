from unittest.mock import AsyncMock

import pytest

from agents.qa_agent.db.unit_of_work import SqlAlchemyQAUnitOfWorkFactory


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
async def test_qa_unit_of_work_commits_explicitly() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async with SqlAlchemyQAUnitOfWorkFactory(_DbManager(session))() as uow:
        assert uow.reports is not None
        assert uow.outbox is not None
        await uow.commit()

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_qa_unit_of_work_rolls_back_on_uncommitted_exit() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async with SqlAlchemyQAUnitOfWorkFactory(_DbManager(session))() as uow:
        assert not uow.completed

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_qa_unit_of_work_rolls_back_on_exception() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with pytest.raises(RuntimeError, match="boom"):
        async with SqlAlchemyQAUnitOfWorkFactory(_DbManager(session))():
            raise RuntimeError("boom")

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
