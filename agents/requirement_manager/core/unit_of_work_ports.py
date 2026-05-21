"""Unit-of-work ports for Requirement Manager application use cases."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from shared.schemas.event import Event

from .meeting_ports import RequirementMeetingStore
from .message_ports import RequirementMessageStore
from .question_ports import RequirementQuestionStore
from .requirement_ports import RequirementStore


class RequirementOutboxWriter(Protocol):
    """Transaction-scoped writer for Requirement integration events."""

    async def stage(self, event: Event) -> None:
        """Stage an event inside the current Requirement transaction."""


class RequirementUnitOfWork(Protocol):
    """Transaction-scoped Requirement persistence boundary."""

    meetings: RequirementMeetingStore
    requirements: RequirementStore
    questions: RequirementQuestionStore
    messages: RequirementMessageStore
    outbox: RequirementOutboxWriter
    completed: bool

    async def commit(self) -> None:
        """Commit successful Requirement mutations and outbox rows."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed Requirement mutations."""


class RequirementUnitOfWorkFactory(Protocol):
    """Factory for transaction-scoped Requirement unit-of-work objects."""

    def __call__(self) -> AbstractAsyncContextManager[RequirementUnitOfWork]:
        """Open one Requirement unit-of-work context."""
