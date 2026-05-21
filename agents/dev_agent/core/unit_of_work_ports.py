"""Unit-of-work ports for Dev agent application use cases."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from .repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort


class DevUnitOfWork(Protocol):
    """Transaction-scoped Dev persistence boundary."""

    tasks: DevTaskRepositoryPort
    workflow_logs: DevWorkflowLogRepositoryPort
    completed: bool

    async def commit(self) -> None:
        """Commit successful task and workflow-log mutations."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed mutations."""


class DevUnitOfWorkFactory(Protocol):
    """Factory for transaction-scoped Dev unit-of-work objects."""

    def __call__(self) -> AbstractAsyncContextManager[DevUnitOfWork]:
        """Open one Dev unit-of-work context."""
