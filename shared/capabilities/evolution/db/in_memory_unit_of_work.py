"""In-memory EvolutionUnitOfWork adapter (DDD-010 impl step).

Implementation follow-up to the DDD-010 seed PR. Twin of the
Coordinator in-memory UoW; mirrors that adapter's shape so the
contract is interchangeable between the two runtimes.

Per ``architecture-principles.md`` §4.1, the UoW owns the transaction
boundary for use cases that touch more than one aggregate or outbox
row in a single commit. This in-memory adapter satisfies the
``EvolutionUnitOfWork`` Protocol by holding references to the
injected seed-store + outbox ports and exposing explicit ``commit``
and ``rollback``.

The production-grade SQLAlchemy-backed adapter lands when the
Evolution capability migrates its multi-aggregate write paths to
the UoW seam.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from ..core.outbox_ports import EvolutionEventOutboxStore
from ..core.seed_ports import EvolutionSkillSeedStore
from ..core.unit_of_work_ports import EvolutionUnitOfWork


class InMemoryEvolutionUnitOfWork(EvolutionUnitOfWork):
    """In-memory EvolutionUnitOfWork for tests + dev paths."""

    def __init__(
        self,
        *,
        seed_store: EvolutionSkillSeedStore,
        outbox: EvolutionEventOutboxStore,
    ) -> None:
        self.seed_store = seed_store
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
async def in_memory_evolution_uow(
    *,
    seed_store: EvolutionSkillSeedStore,
    outbox: EvolutionEventOutboxStore,
) -> AsyncIterator[InMemoryEvolutionUnitOfWork]:
    """Async-context factory matching EvolutionUnitOfWorkFactory.

    Auto-commits on clean exit; rolls back + re-raises on exception.
    """
    uow = InMemoryEvolutionUnitOfWork(seed_store=seed_store, outbox=outbox)
    try:
        yield uow
        if not uow.completed:
            await uow.commit()
    except Exception:
        await uow.rollback()
        raise
