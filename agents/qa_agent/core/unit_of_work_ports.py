"""Unit-of-work ports for QA acceptance application use cases."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from shared.schemas.event import Event

from .report_store import QAReportStore


class QAAcceptanceOutboxWriter(Protocol):
    """Transaction-scoped writer for QA integration events."""

    async def stage(self, event: Event) -> None:
        """Stage an event inside the current acceptance transaction."""


class QAUnitOfWork(Protocol):
    """Transaction-scoped QA persistence boundary."""

    reports: QAReportStore
    outbox: QAAcceptanceOutboxWriter
    completed: bool

    async def commit(self) -> None:
        """Commit successful acceptance result and outbox mutations."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed acceptance mutations."""


class QAUnitOfWorkFactory(Protocol):
    """Factory for transaction-scoped QA unit-of-work objects."""

    def __call__(self) -> AbstractAsyncContextManager[QAUnitOfWork]:
        """Open one QA unit-of-work context."""
