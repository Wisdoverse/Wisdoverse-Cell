"""SQLAlchemy unit-of-work implementation for Requirement Manager use cases."""

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.event import Event

from ..core.feedback_ports import RequirementFeedbackStore
from ..core.meeting_ports import RequirementMeetingStore
from ..core.message_ports import RequirementMessageStore
from ..core.outbox_ports import RequirementEventOutboxStore
from ..core.question_ports import RequirementQuestionStore
from ..core.requirement_ports import RequirementStore
from ..core.unit_of_work_ports import RequirementOutboxWriter, RequirementUnitOfWork
from .database import DatabaseManager
from .feedback_store import SqlAlchemyRequirementFeedbackStore
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


class SqlAlchemyRequirementSessionOutboxWriter(RequirementOutboxWriter):
    """Outbox writer for a caller-owned legacy session."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        outbox_store: RequirementEventOutboxStore,
    ) -> None:
        self._session = session
        self._outbox_store = outbox_store

    async def stage(self, event: Event) -> None:
        await self._outbox_store.stage(self._session, event)


class SqlAlchemyRequirementUnitOfWork(RequirementUnitOfWork):
    """Session-scoped Requirement stores with explicit commit and rollback."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self.meetings = SqlAlchemyRequirementMeetingStore(session)
        self.requirements = SqlAlchemyRequirementStore(session)
        self.questions = SqlAlchemyRequirementQuestionStore(session)
        self.messages = SqlAlchemyRequirementMessageStore(session)
        self.feedback = SqlAlchemyRequirementFeedbackStore(session)
        self.outbox = SqlAlchemyRequirementOutboxWriter(session)
        self.completed = False

    async def commit(self) -> None:
        result = self._session.commit()
        if inspect.isawaitable(result):
            await result
        self.completed = True

    async def rollback(self) -> None:
        result = self._session.rollback()
        if inspect.isawaitable(result):
            await result
        self.completed = True


class SqlAlchemyRequirementSessionUnitOfWork(RequirementUnitOfWork):
    """Compatibility UOW for callers that still own the SQLAlchemy session."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        outbox_store: RequirementEventOutboxStore,
        meetings: RequirementMeetingStore | None = None,
        requirements: RequirementStore | None = None,
        questions: RequirementQuestionStore | None = None,
        messages: RequirementMessageStore | None = None,
        feedback: RequirementFeedbackStore | None = None,
    ) -> None:
        self._session = session
        self.meetings = (
            meetings
            if meetings is not None
            else SqlAlchemyRequirementMeetingStore(session)
        )
        self.requirements = (
            requirements
            if requirements is not None
            else SqlAlchemyRequirementStore(session)
        )
        self.questions = (
            questions
            if questions is not None
            else SqlAlchemyRequirementQuestionStore(session)
        )
        self.messages = (
            messages
            if messages is not None
            else SqlAlchemyRequirementMessageStore(session)
        )
        self.feedback = (
            feedback
            if feedback is not None
            else SqlAlchemyRequirementFeedbackStore(session)
        )
        self.outbox = SqlAlchemyRequirementSessionOutboxWriter(
            session=session,
            outbox_store=outbox_store,
        )
        self.completed = False

    async def commit(self) -> None:
        result = self._session.commit()
        if inspect.isawaitable(result):
            await result
        self.completed = True

    async def rollback(self) -> None:
        result = self._session.rollback()
        if inspect.isawaitable(result):
            await result
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
