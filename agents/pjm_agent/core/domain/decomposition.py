"""Decomposition aggregate.

Stage 2 (domain modeling) per docs/architecture/migration-plan.md.
Promotes the decomposition lifecycle from a constants module to an
explicit aggregate. The aggregate owns:

- Identity (``wp_id``).
- The current ``status`` value.
- The set of legal next states, derived from the lifecycle policy.
- The transition-and-event protocol: ``transition_to`` mutates the
  status and emits a ``DecompositionStatusChanged`` domain event,
  raising ``InvalidDecompositionTransitionError`` for illegal moves.

Adoption is gradual. Use cases that currently set ``record.status =
"approved"`` and then call ``decomposition.update_status(wp_id,
"approved")`` will move, one site at a time, to constructing the
aggregate, calling ``aggregate.transition_to(APPROVED)``, then
flushing the new status through the existing persistence path.

Domain-events list returned by ``pull_events`` is the seam that the
outbox-write step in the application layer will consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lifecycle.decomposition_lifecycle import (
    DECOMPOSITION_STATUSES,
    can_transition,
    is_terminal,
)


class InvalidDecompositionTransitionError(Exception):
    """Raised when ``transition_to`` is called with an illegal target state."""

    def __init__(self, *, wp_id: int, from_status: str, to_status: str) -> None:
        super().__init__(
            f"illegal decomposition transition wp_id={wp_id} "
            f"{from_status} -> {to_status}"
        )
        self.wp_id = wp_id
        self.from_status = from_status
        self.to_status = to_status


@dataclass(frozen=True, slots=True)
class DecompositionStatusChanged:
    """Domain event emitted when the aggregate moves between states."""

    wp_id: int
    from_status: str
    to_status: str


@dataclass(slots=True)
class Decomposition:
    """Aggregate for a work-package decomposition record."""

    wp_id: int
    status: str
    pending_events: list[DecompositionStatusChanged] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in DECOMPOSITION_STATUSES:
            raise ValueError(
                f"unknown decomposition status {self.status!r}; "
                f"must be one of {DECOMPOSITION_STATUSES}"
            )

    def transition_to(self, new_status: str) -> DecompositionStatusChanged:
        """Move the aggregate to ``new_status`` if the transition is legal.

        Raises:
            InvalidDecompositionTransitionError: if the lifecycle policy
                does not allow this transition.
        """
        if new_status not in DECOMPOSITION_STATUSES:
            raise InvalidDecompositionTransitionError(
                wp_id=self.wp_id,
                from_status=self.status,
                to_status=new_status,
            )
        if not can_transition(self.status, new_status):
            raise InvalidDecompositionTransitionError(
                wp_id=self.wp_id,
                from_status=self.status,
                to_status=new_status,
            )
        event = DecompositionStatusChanged(
            wp_id=self.wp_id,
            from_status=self.status,
            to_status=new_status,
        )
        self.status = new_status
        self.pending_events.append(event)
        return event

    def is_terminal(self) -> bool:
        """Return whether the aggregate sits in a terminal state."""
        return is_terminal(self.status)

    def pull_events(self) -> list[DecompositionStatusChanged]:
        """Drain pending domain events, leaving the aggregate empty."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


__all__ = [
    "Decomposition",
    "DecompositionStatusChanged",
    "InvalidDecompositionTransitionError",
]
