"""SQLAlchemy unit-of-work implementation for Dev agent use cases."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.unit_of_work_ports import DevUnitOfWork
from .database import DatabaseManager
from .task_store import SqlAlchemyDevTaskStore
from .workflow_log_store import SqlAlchemyDevWorkflowLogStore


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
