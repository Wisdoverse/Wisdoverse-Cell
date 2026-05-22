"""SQLAlchemy unit-of-work implementation for QA acceptance use cases."""

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..core.outbox_ports import QAEventOutboxStore
from ..core.unit_of_work_ports import QAAcceptanceOutboxWriter, QAUnitOfWork
from .database import DatabaseManager
from .report_store import SqlAlchemyQAReportStore
from .repository import QAEventOutboxRepository


class SqlAlchemyQAAcceptanceOutboxWriter(QAAcceptanceOutboxWriter):
    """Transaction-scoped QA outbox writer."""

    def __init__(self, session: AsyncSession):
        self._outbox = QAEventOutboxRepository(session)

    async def stage(self, event: Event) -> None:
        await self._outbox.add(event)


class SqlAlchemyQAUnitOfWork(QAUnitOfWork):
    """Session-scoped QA stores with explicit commit and rollback."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self.reports = SqlAlchemyQAReportStore(session)
        self.outbox = SqlAlchemyQAAcceptanceOutboxWriter(session)
        self.completed = False

    async def commit(self) -> None:
        await self._session.commit()
        self.completed = True

    async def rollback(self) -> None:
        await self._session.rollback()
        self.completed = True


class SqlAlchemyQASessionOutboxWriter(QAAcceptanceOutboxWriter):
    """Compatibility outbox writer for caller-owned legacy sessions."""

    def __init__(
        self,
        session: object,
        *,
        outbox_store: QAEventOutboxStore,
    ) -> None:
        self._session = session
        self._outbox_store = outbox_store

    async def stage(self, event: Event) -> None:
        await self._outbox_store.stage(self._session, event)


class SqlAlchemyQASessionUnitOfWork(QAUnitOfWork):
    """Compatibility UOW for DB managers that expose only session()."""

    def __init__(
        self,
        session: object,
        *,
        outbox_store: QAEventOutboxStore,
    ) -> None:
        self._session = session
        self.reports = SqlAlchemyQAReportStore(session)
        self.outbox = SqlAlchemyQASessionOutboxWriter(
            session,
            outbox_store=outbox_store,
        )
        self.completed = False

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


class SqlAlchemyQAUnitOfWorkFactory:
    """Create explicit QA unit-of-work contexts from the runtime DB manager."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[QAUnitOfWork]:
        async with self._db_manager.async_session() as session:
            uow = SqlAlchemyQAUnitOfWork(session)
            try:
                yield uow
            except Exception:
                if not uow.completed:
                    await uow.rollback()
                raise
            finally:
                if not uow.completed:
                    await uow.rollback()


class SqlAlchemyQASessionUnitOfWorkFactory:
    """Create QA UOW contexts for legacy DB managers with session()."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        *,
        outbox_store: QAEventOutboxStore,
    ) -> None:
        self._db_manager = db_manager
        self._outbox_store = outbox_store

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[QAUnitOfWork]:
        async with self._db_manager.session() as session:
            uow = SqlAlchemyQASessionUnitOfWork(
                session,
                outbox_store=self._outbox_store,
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
