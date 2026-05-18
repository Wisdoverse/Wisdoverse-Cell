"""Requirement aggregate.

Stage 2 (domain modeling) per docs/architecture/migration-plan.md.
Promotes the requirement lifecycle to an explicit aggregate, mirroring
PJM Decomposition (#137) and Dev Task (#138).

Adoption is gradual. The existing `mark_confirmed` / `mark_rejected` /
`record_updated` helpers in
``agents.requirement_manager.core.domain.lifecycle.requirement_lifecycle``
keep working; future PRs route their callers through the aggregate so
the transition validation and domain-event buffer become the single
source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lifecycle.requirement_states import (
    REQUIREMENT_STATUSES,
    can_transition,
    is_terminal,
)


class InvalidRequirementTransitionError(Exception):
    """Raised when ``transition_to`` is called with an illegal target."""

    def __init__(
        self, *, requirement_id: str, from_status: str, to_status: str
    ) -> None:
        super().__init__(
            f"illegal requirement transition requirement_id={requirement_id} "
            f"{from_status} -> {to_status}"
        )
        self.requirement_id = requirement_id
        self.from_status = from_status
        self.to_status = to_status


@dataclass(frozen=True, slots=True)
class RequirementStatusChanged:
    """Domain event emitted when the aggregate moves between states."""

    requirement_id: str
    from_status: str
    to_status: str
    actor_id: str | None = None


@dataclass(slots=True)
class Requirement:
    """Aggregate for one requirement record."""

    requirement_id: str
    status: str
    pending_events: list[RequirementStatusChanged] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in REQUIREMENT_STATUSES:
            raise ValueError(
                f"unknown requirement status {self.status!r}; "
                f"must be one of {REQUIREMENT_STATUSES}"
            )

    def transition_to(
        self, new_status: str, *, actor_id: str | None = None
    ) -> RequirementStatusChanged:
        """Move the aggregate to ``new_status`` if the transition is legal.

        Raises:
            InvalidRequirementTransitionError: if the lifecycle policy
                does not allow this transition.
        """
        if new_status not in REQUIREMENT_STATUSES or not can_transition(
            self.status, new_status
        ):
            raise InvalidRequirementTransitionError(
                requirement_id=self.requirement_id,
                from_status=self.status,
                to_status=new_status,
            )
        event = RequirementStatusChanged(
            requirement_id=self.requirement_id,
            from_status=self.status,
            to_status=new_status,
            actor_id=actor_id,
        )
        self.status = new_status
        self.pending_events.append(event)
        return event

    def is_terminal(self) -> bool:
        """Return whether the requirement sits in a terminal state."""
        return is_terminal(self.status)

    def pull_events(self) -> list[RequirementStatusChanged]:
        """Drain pending domain events, leaving the aggregate empty."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


__all__ = [
    "InvalidRequirementTransitionError",
    "Requirement",
    "RequirementStatusChanged",
]
