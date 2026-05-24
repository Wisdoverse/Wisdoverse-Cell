"""SQLAlchemy unit-of-work implementation for Dev agent use cases."""

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..core.outbox_ports import DevEventOutboxStore
from ..core.repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort
from ..core.unit_of_work_ports import DevReconcileLockPort, DevUnitOfWork
from .database import DatabaseManager
from .outbox_store import SqlAlchemyDevEventOutboxSessionStore
from .reconcile_lock import SqlAlchemyDevReconcileLock
from .task_store import SqlAlchemyDevTaskStore
from .workflow_log_store import SqlAlchemyDevWorkflowLogStore


class NoopDevReconcileLock(DevReconcileLockPort):
    """In-memory reconcile lock for injected tests."""

    async def try_acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


class NoopDevEventOutboxStore(DevEventOutboxStore):
    """In-memory outbox placeholder for injected tests."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    async def add(self, event: Event) -> None:
        self.events.append(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        return self.events[:limit]

    async def mark_published(self, event_id: str) -> None:
        return None

    async def mark_failed(self, event_id: str, error: str) -> None:
        return None


class InjectedDevUnitOfWork(DevUnitOfWork):
    """Unit-of-work adapter for tests and callers that inject repository doubles."""

    def __init__(
        self,
        *,
        tasks: DevTaskRepositoryPort,
        workflow_logs: DevWorkflowLogRepositoryPort,
        outbox: DevEventOutboxStore | None = None,
        reconcile_lock: DevReconcileLockPort | None = None,
    ) -> None:
        self.tasks = tasks
        self.workflow_logs = workflow_logs
        self.outbox = outbox if outbox is not None else NoopDevEventOutboxStore()
        self.reconcile_lock = (
            reconcile_lock if reconcile_lock is not None else NoopDevReconcileLock()
        )
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
        outbox: DevEventOutboxStore | None = None,
        reconcile_lock: DevReconcileLockPort | None = None,
    ) -> None:
        super().__init__(
            tasks=tasks if tasks is not None else SqlAlchemyDevTaskStore(session),
            workflow_logs=(
                workflow_logs
                if workflow_logs is not None
                else SqlAlchemyDevWorkflowLogStore(session)
            ),
            outbox=outbox
            if outbox is not None
            else SqlAlchemyDevEventOutboxSessionStore(session),
            reconcile_lock=reconcile_lock
            if reconcile_lock is not None
            else SqlAlchemyDevReconcileLock(session),
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
        self.outbox = SqlAlchemyDevEventOutboxSessionStore(session)
        self.reconcile_lock = SqlAlchemyDevReconcileLock(session)
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
        outbox: DevEventOutboxStore | None = None,
        reconcile_lock: DevReconcileLockPort | None = None,
    ) -> None:
        self._tasks = tasks
        self._workflow_logs = workflow_logs
        self._outbox = outbox
        self._reconcile_lock = reconcile_lock

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[DevUnitOfWork]:
        uow = InjectedDevUnitOfWork(
            tasks=self._tasks,
            workflow_logs=self._workflow_logs,
            outbox=self._outbox,
            reconcile_lock=self._reconcile_lock,
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
