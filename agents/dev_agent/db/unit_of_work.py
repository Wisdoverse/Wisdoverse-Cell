"""SQLAlchemy unit-of-work implementation for Dev agent use cases."""

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort
from ..core.unit_of_work_ports import DevUnitOfWork
from .database import DatabaseManager
from .task_store import SqlAlchemyDevTaskStore
from .workflow_log_store import SqlAlchemyDevWorkflowLogStore


class InjectedDevUnitOfWork(DevUnitOfWork):
    """Unit-of-work adapter for tests and callers that inject repository doubles."""

    def __init__(
        self,
        *,
        tasks: DevTaskRepositoryPort,
        workflow_logs: DevWorkflowLogRepositoryPort,
    ) -> None:
        self.tasks = tasks
        self.workflow_logs = workflow_logs
        self.completed = False

    async def commit(self) -> None:
        self.completed = True

    async def rollback(self) -> None:
        self.completed = True


class SqlAlchemyDevSessionUnitOfWork(InjectedDevUnitOfWork):
    """Compatibility UOW for DB managers that expose only session()."""

    def __init__(
        self,
        *,
        session: object,
        tasks: DevTaskRepositoryPort | None = None,
        workflow_logs: DevWorkflowLogRepositoryPort | None = None,
    ) -> None:
        super().__init__(
            tasks=tasks if tasks is not None else SqlAlchemyDevTaskStore(session),
            workflow_logs=(
                workflow_logs
                if workflow_logs is not None
                else SqlAlchemyDevWorkflowLogStore(session)
            ),
        )
        self._session = session

    async def commit(self) -> None:
        result = self._session.commit()
        if inspect.isawaitable(result):
            await result
        self.completed = True

    async def rollback(self) -> None:
        rollback = getattr(self._session, "rollback", None)
        if rollback is not None:
            result = rollback()
            if inspect.isawaitable(result):
                await result
        self.completed = True


class SqlAlchemyDevUnitOfWork(DevUnitOfWork):
    """Session-scoped Dev stores with explicit commit and rollback."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self.tasks = SqlAlchemyDevTaskStore(session)
        self.workflow_logs = SqlAlchemyDevWorkflowLogStore(session)
        self.completed = False

    async def commit(self) -> None:
        await self._session.commit()
        self.completed = True

    async def rollback(self) -> None:
        await self._session.rollback()
        self.completed = True


class SqlAlchemyDevUnitOfWorkFactory:
    """Create explicit Dev unit-of-work contexts from the runtime DB manager."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[DevUnitOfWork]:
        async with self._db_manager.async_session() as session:
            uow = SqlAlchemyDevUnitOfWork(session)
            try:
                yield uow
            except Exception:
                if not uow.completed:
                    await uow.rollback()
                raise
            finally:
                if not uow.completed:
                    await uow.rollback()


class InjectedDevUnitOfWorkFactory:
    """Create Dev UOW contexts from injected repository ports."""

    def __init__(
        self,
        *,
        tasks: DevTaskRepositoryPort,
        workflow_logs: DevWorkflowLogRepositoryPort,
    ) -> None:
        self._tasks = tasks
        self._workflow_logs = workflow_logs

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[DevUnitOfWork]:
        uow = InjectedDevUnitOfWork(
            tasks=self._tasks,
            workflow_logs=self._workflow_logs,
        )
        try:
            yield uow
        except Exception:
            if not uow.completed:
                await uow.rollback()
            raise
        finally:
            if not uow.completed:
                await uow.rollback()


class SqlAlchemyDevSessionUnitOfWorkFactory:
    """Create Dev UOW contexts for legacy DB managers with session()."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[DevUnitOfWork]:
        async with self._db_manager.session() as session:
            uow = SqlAlchemyDevSessionUnitOfWork(session=session)
            try:
                yield uow
            except Exception:
                if not uow.completed:
                    await uow.rollback()
                raise
            finally:
                if not uow.completed:
                    await uow.rollback()
