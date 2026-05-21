"""SQLAlchemy unit-of-work implementation for Requirement Manager use cases."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..core.unit_of_work_ports import RequirementOutboxWriter, RequirementUnitOfWork
from .database import DatabaseManager
from .meeting_store import SqlAlchemyRequirementMeetingStore
from .message_store import SqlAlchemyRequirementMessageStore
from .question_store import SqlAlchemyRequirementQuestionStore
from .repository import RequirementEventOutboxRepository
from .requirement_store import SqlAlchemyRequirementStore


class SqlAlchemyRequirementOutboxWriter(RequirementOutboxWriter):
    """Transaction-scoped Requirement outbox writer."""

    def __init__(self, session: AsyncSession):
        self._outbox = RequirementEventOutboxRepository(session)

    async def stage(self, event: Event) -> None:
        await self._outbox.add(event)


class SqlAlchemyRequirementUnitOfWork(RequirementUnitOfWork):
    """Session-scoped Requirement stores with explicit commit and rollback."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self.meetings = SqlAlchemyRequirementMeetingStore(session)
        self.requirements = SqlAlchemyRequirementStore(session)
        self.questions = SqlAlchemyRequirementQuestionStore(session)
        self.messages = SqlAlchemyRequirementMessageStore(session)
        self.outbox = SqlAlchemyRequirementOutboxWriter(session)
        self.completed = False

    async def commit(self) -> None:
        await self._session.commit()
        self.completed = True

    async def rollback(self) -> None:
        await self._session.rollback()
        self.completed = True


class SqlAlchemyRequirementUnitOfWorkFactory:
    """Create explicit Requirement unit-of-work contexts from the runtime DB manager."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[RequirementUnitOfWork]:
        async with self._db_manager.async_session() as session:
            uow = SqlAlchemyRequirementUnitOfWork(session)
            try:
                yield uow
            except Exception:
                if not uow.completed:
                    await uow.rollback()
                raise
            finally:
                if not uow.completed:
                    await uow.rollback()
