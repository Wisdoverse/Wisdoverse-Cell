"""SyncOperation aggregate seed (DDD-003).

Seeds the explicit aggregate-class pattern for the Sync capability per
``architecture-principles.md`` §1 Domain layer / §4.8
(Aggregate-Raised Domain Events) / §4.10 (State Machines), and audit
row DDD-003.

The Sync capability today drives behaviour off string-status comparisons
in ``shared/capabilities/sync/core/engine.py:74-87``
(``if op_status == "failed" or feishu_status == "failed"``) — the
H4 / P1-2 anti-pattern documented in the Phase 1 audit. This module
introduces the typed alternative.

Sync currently runs two sub-boundaries (OpenProject side, Feishu Bitable
side) inside one runtime. Per DDD-014 the sub-boundaries split into
separate runtimes; this aggregate carries a ``side`` discriminator so
the same domain class serves both during the modular-monolith phase.
After DDD-014 lands, each side keeps its own aggregate file.

This is a **seed** PR: the aggregate class lives alongside the existing
string-status engine; engine migration follows in dedicated PRs (one
per sub-boundary) per ``architecture-principles.md`` §3 ("no mass file
moves").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SyncSide(StrEnum):
    """Which sub-boundary this operation runs against."""

    OPENPROJECT = "openproject"
    FEISHU_BITABLE = "feishu_bitable"


class SyncOperationStatus(StrEnum):
    """Typed status for a SyncOperation aggregate.

    Replaces the string-status comparisons in
    ``shared/capabilities/sync/core/engine.py`` (DDD-003).
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvalidSyncOperationTransitionError(ValueError):
    """Raised when a SyncOperation state transition is not allowed by the FSM."""


VALID_TRANSITIONS: dict[SyncOperationStatus, frozenset[SyncOperationStatus]] = {
    SyncOperationStatus.PENDING: frozenset(
        {SyncOperationStatus.RUNNING, SyncOperationStatus.SKIPPED}
    ),
    SyncOperationStatus.RUNNING: frozenset(
        {
            SyncOperationStatus.SUCCEEDED,
            SyncOperationStatus.PARTIAL_FAILURE,
            SyncOperationStatus.FAILED,
        }
    ),
    SyncOperationStatus.SUCCEEDED: frozenset(),
    SyncOperationStatus.PARTIAL_FAILURE: frozenset(),
    SyncOperationStatus.FAILED: frozenset(),
    SyncOperationStatus.SKIPPED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class SyncOperationStatusChanged:
    """In-memory domain event raised by SyncOperation.transition_to()."""

    operation_id: str
    side: SyncSide
    from_status: SyncOperationStatus
    to_status: SyncOperationStatus
    processed_count: int


@dataclass
class SyncOperation:
    """SyncOperation aggregate root.

    One instance represents one run of the sync engine on one
    sub-boundary (OpenProject or Feishu Bitable). Owns the FSM, the
    processed-count tally, and the in-memory domain-event buffer.
    """

    operation_id: str
    side: SyncSide
    status: SyncOperationStatus = SyncOperationStatus.PENDING
    processed_count: int = 0
    _events: list[SyncOperationStatusChanged] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        """True when the aggregate cannot transition further."""
        return not VALID_TRANSITIONS[self.status]

    def transition_to(
        self,
        target: SyncOperationStatus,
        *,
        processed_delta: int = 0,
    ) -> None:
        """Move the aggregate to a new status if permitted by the FSM."""
        if target not in VALID_TRANSITIONS[self.status]:
            raise InvalidSyncOperationTransitionError(
                f"SyncOperation {self.operation_id} ({self.side}): illegal "
                f"transition {self.status} -> {target}"
            )
        previous = self.status
        self.status = target
        self.processed_count += processed_delta
        self._events.append(
            SyncOperationStatusChanged(
                operation_id=self.operation_id,
                side=self.side,
                from_status=previous,
                to_status=target,
                processed_count=self.processed_count,
            )
        )

    def pull_events(self) -> list[SyncOperationStatusChanged]:
        """Drain raised domain events. Use case forwards them to the outbox."""
        drained = list(self._events)
        self._events.clear()
        return drained


def combine_side_statuses(
    op_status: SyncOperationStatus,
    feishu_status: SyncOperationStatus,
) -> SyncOperationStatus:
    """Combine two sub-boundary outcomes into one terminal status.

    Replaces the string-comparison logic in
    ``shared/capabilities/sync/core/engine.py:74-87``. Use this helper
    once engine.py migrates to the typed enum (follow-up PR).
    """
    if op_status == SyncOperationStatus.FAILED and feishu_status == SyncOperationStatus.FAILED:
        return SyncOperationStatus.FAILED
    if op_status == SyncOperationStatus.FAILED or feishu_status == SyncOperationStatus.FAILED:
        return SyncOperationStatus.PARTIAL_FAILURE
    if (
        op_status == SyncOperationStatus.SUCCEEDED
        and feishu_status == SyncOperationStatus.SUCCEEDED
    ):
        return SyncOperationStatus.SUCCEEDED
    return SyncOperationStatus.PARTIAL_FAILURE
