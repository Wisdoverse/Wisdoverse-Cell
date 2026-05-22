"""Unit-of-work ports for Evolution capability application use cases.

Seeds the explicit transaction-boundary pattern per
``architecture-principles.md`` §4.1 (Use Cases) and audit row DDD-010.

Evolution capability use cases that touch more than one aggregate or
row in a single transaction (proposal mutation + outbox publish;
seed-bootstrap + audit-event emit) need an explicit transactional
seam rather than the implicit session-context boundary used today.

This module defines the contract; concrete adapters land in
``shared/capabilities/evolution/db/``. Per-caller migration follows in
follow-up PRs so each migration stays reviewable per
``architecture-principles.md`` §3 ("no mass file moves").
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from .outbox_ports import EvolutionEventOutboxStore
from .seed_ports import EvolutionSkillSeedStore


class EvolutionUnitOfWork(Protocol):
    """Transaction-scoped Evolution persistence boundary.

    Spans the skill-seed store and event outbox. Use cases that write
    proposal mutations alongside outbox enqueue (e.g. approval flows
    that emit `evolution.proposal-approved`) consume the UoW instead
    of the individual ports.

    The `EvolutionProposal` record itself lives in the Control Plane;
    cross-context writes (proposal commit + capability-side outbox)
    are coordinated via this UoW plus the
    `ControlPlaneEvolutionProposalStore` from
    `evolution_proposal_ports.py` so the capability never crosses the
    Control Plane transaction boundary directly.
    """

    seed_store: EvolutionSkillSeedStore
    outbox: EvolutionEventOutboxStore
    completed: bool

    async def commit(self) -> None:
        """Commit successful evolution-capability mutations."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed mutations."""


class EvolutionUnitOfWorkFactory(Protocol):
    """Factory for transaction-scoped Evolution unit-of-work objects."""

    def __call__(self) -> AbstractAsyncContextManager[EvolutionUnitOfWork]:
        """Open one Evolution unit-of-work context."""
