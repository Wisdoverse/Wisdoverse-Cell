"""Unit-of-work ports for Dev agent application use cases."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from .outbox_ports import DevEventOutboxStore
from .repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort


class DevReconcileLockPort(Protocol):
    """Lock used by scheduled reconciliation to keep one active runner."""

    async def try_acquire(self) -> bool:
        """Return whether this scheduler instance acquired the reconcile lock."""

    async def release(self) -> None:
        """Release the reconcile lock if it was acquired."""


class DevUnitOfWork(Protocol):
    """Transaction-scoped Dev persistence boundary."""

    tasks: DevTaskRepositoryPort
    workflow_logs: DevWorkflowLogRepositoryPort
    outbox: DevEventOutboxStore
    reconcile_lock: DevReconcileLockPort
    completed: bool

    async def commit(self) -> None:
        """Commit successful task and workflow-log mutations."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed mutations."""


class DevUnitOfWorkFactory(Protocol):
    """Factory for transaction-scoped Dev unit-of-work objects."""

    def __call__(self) -> AbstractAsyncContextManager[DevUnitOfWork]:
        """Open one Dev unit-of-work context."""
