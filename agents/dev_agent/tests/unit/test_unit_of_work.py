from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.dev_agent.db.unit_of_work import (
    InjectedDevUnitOfWorkFactory,
    SqlAlchemyDevSessionUnitOfWorkFactory,
    SqlAlchemyDevUnitOfWorkFactory,
)


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


class _LegacyDbManager:
    def __init__(self, session):
        self._session = session

    def session(self):
        return _SessionContext(self._session)


@pytest.mark.asyncio
async def test_dev_unit_of_work_commits_explicitly() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async with SqlAlchemyDevUnitOfWorkFactory(_DbManager(session))() as uow:
        assert uow.tasks is not None
        assert uow.workflow_logs is not None
        await uow.commit()

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_dev_unit_of_work_rolls_back_on_uncommitted_exit() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async with SqlAlchemyDevUnitOfWorkFactory(_DbManager(session))() as uow:
        assert not uow.completed

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_dev_session_unit_of_work_factory_adapts_legacy_session() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async with SqlAlchemyDevSessionUnitOfWorkFactory(_LegacyDbManager(session))() as uow:
        assert uow.tasks is not None
        assert uow.workflow_logs is not None
        await uow.commit()

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_injected_dev_unit_of_work_factory_uses_repository_ports() -> None:
    tasks = MagicMock()
    workflow_logs = MagicMock()

    async with InjectedDevUnitOfWorkFactory(
        tasks=tasks,
        workflow_logs=workflow_logs,
    )() as uow:
        assert uow.tasks is tasks
        assert uow.workflow_logs is workflow_logs
        await uow.commit()

    assert uow.completed


@pytest.mark.asyncio
async def test_dev_unit_of_work_rolls_back_on_exception() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with pytest.raises(RuntimeError, match="boom"):
        async with SqlAlchemyDevUnitOfWorkFactory(_DbManager(session))():
            raise RuntimeError("boom")

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
