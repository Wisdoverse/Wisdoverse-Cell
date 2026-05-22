"""In-memory CoordinatorUnitOfWork adapter (DDD-010 impl step).

Implementation follow-up to the DDD-010 seed PR. Provides a concrete
``CoordinatorUnitOfWork`` for unit-test injection and dev paths
before a production-grade SQLAlchemy-backed UoW lands as part of the
ADR-0008 (DDD-018) execution sequence.

Per ``architecture-principles.md`` §4.1, the UoW owns the transaction
boundary for use cases that touch more than one aggregate or outbox
row in a single commit. This in-memory adapter satisfies the
``CoordinatorUnitOfWork`` Protocol by delegating to the injected
state + outbox ports and exposing explicit ``commit`` / ``rollback``
methods.

When the Postgres-backed durable state store from ADR-0008 lands,
its SQLAlchemy session is wired here so ``commit()`` flushes both
state and outbox writes atomically.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from ..core.outbox_ports import CoordinatorEventOutboxStore
from ..core.state_ports import CoordinatorStateStorePort
from ..core.unit_of_work_ports import CoordinatorUnitOfWork


class InMemoryCoordinatorUnitOfWork(CoordinatorUnitOfWork):
    """In-memory CoordinatorUnitOfWork for tests and the dev path.

    Holds references to the injected state and outbox stores.
    ``commit()`` and ``rollback()`` are tracked locally; the real
    Postgres-backed adapter (ADR-0008) overrides these to drive the
    SQLAlchemy session.
    """

    def __init__(
        self,
        *,
        state_store: CoordinatorStateStorePort,
        outbox: CoordinatorEventOutboxStore,
    ) -> None:
        self.state_store = state_store
        self.outbox = outbox
        self.completed = False
        self._rolled_back = False

    async def commit(self) -> None:
        """Mark the UoW committed. Real adapter flushes the session here."""
        if self._rolled_back:
            raise RuntimeError("cannot commit a rolled-back unit of work")
        self.completed = True

    async def rollback(self) -> None:
        """Mark the UoW rolled back. Real adapter aborts the session here."""
        self._rolled_back = True
        self.completed = False


@asynccontextmanager
async def in_memory_coordinator_uow(
    *,
    state_store: CoordinatorStateStorePort,
    outbox: CoordinatorEventOutboxStore,
) -> AsyncIterator[InMemoryCoordinatorUnitOfWork]:
    """Async-context factory matching CoordinatorUnitOfWorkFactory.

    On clean exit calls ``commit()``; on exception calls ``rollback()``.
    """
    uow = InMemoryCoordinatorUnitOfWork(state_store=state_store, outbox=outbox)
    try:
        yield uow
        if not uow.completed:
            await uow.commit()
    except Exception:
        await uow.rollback()
        raise
