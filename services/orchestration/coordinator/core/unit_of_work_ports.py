"""Unit-of-work ports for Coordinator application use cases.

Seeds the explicit transaction-boundary pattern per
``architecture-principles.md`` §4.1 (Use Cases) and audit row DDD-010.

Coordinator use cases that touch more than one aggregate or outbox row
in a single transaction (state-store update + outbox publish; decision
persist + scratchpad compaction) need an explicit transactional seam
rather than the implicit session-context boundary used today.

This module defines the contract; concrete adapters land in
`services/orchestration/coordinator/db/` alongside the existing
`outbox_store.py` and `state_store.py`. Per-caller migration follows in
follow-up PRs so each migration stays reviewable per
``architecture-principles.md`` §3 ("no mass file moves").
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from .outbox_ports import CoordinatorEventOutboxStore
from .state_ports import CoordinatorStateStorePort


class CoordinatorUnitOfWork(Protocol):
    """Transaction-scoped Coordinator persistence boundary.

    Spans the state store and event outbox. Use cases that write to
    both in a single commit (decision persist + outbox enqueue;
    workflow-state update + dispatch event) consume the UoW instead of
    the individual ports.
    """

    state_store: CoordinatorStateStorePort
    outbox: CoordinatorEventOutboxStore
    completed: bool

    async def commit(self) -> None:
        """Commit successful coordinator mutations."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed mutations."""


class CoordinatorUnitOfWorkFactory(Protocol):
    """Factory for transaction-scoped Coordinator unit-of-work objects."""

    def __call__(self) -> AbstractAsyncContextManager[CoordinatorUnitOfWork]:
        """Open one Coordinator unit-of-work context."""
