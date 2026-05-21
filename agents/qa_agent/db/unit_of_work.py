"""SQLAlchemy unit-of-work implementation for QA acceptance use cases."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

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
