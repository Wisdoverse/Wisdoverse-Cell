"""Dev task aggregate.

Stage 2 (domain modeling) per docs/architecture/migration-plan.md.
Promotes the dev task lifecycle from a constants module to an
explicit aggregate. Mirrors the pattern landed for PJM Decomposition
in #137 so the per-runtime aggregates stay coherent.

The aggregate owns:

- Identity (``task_id``).
- The current ``status`` value.
- The transition-and-event protocol: ``transition_to`` mutates the
  status and emits a ``TaskStatusChanged`` domain event, raising
  ``InvalidTaskTransitionError`` for illegal moves.

Adoption is gradual. Use cases and stores continue to call
``can_transition`` directly until they are migrated one site at a
time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lifecycle.task_lifecycle import (
    ACTIVE_STATUSES,
    IN_PROGRESS_STATUSES,
    VALID_TRANSITIONS,
    can_transition,
)


class InvalidTaskTransitionError(Exception):
    """Raised when ``transition_to`` is called with an illegal target state."""

    def __init__(self, *, task_id: str, from_status: str, to_status: str) -> None:
        super().__init__(
            f"illegal dev task transition task_id={task_id} "
            f"{from_status} -> {to_status}"
        )
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status


@dataclass(frozen=True, slots=True)
class TaskStatusChanged:
    """Domain event emitted when the aggregate moves between states."""

    task_id: str
    from_status: str
    to_status: str


@dataclass(slots=True)
class Task:
    """Aggregate for one delivery task."""

    task_id: str
    status: str
    pending_events: list[TaskStatusChanged] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in VALID_TRANSITIONS:
            raise ValueError(
                f"unknown dev task status {self.status!r}; "
                f"must be one of {tuple(VALID_TRANSITIONS)}"
            )

    def transition_to(self, new_status: str) -> TaskStatusChanged:
        """Move the aggregate to ``new_status`` if the transition is legal.

        Raises:
            InvalidTaskTransitionError: if the lifecycle policy
                does not allow this transition.
        """
        if new_status not in VALID_TRANSITIONS or not can_transition(
            self.status, new_status
        ):
            raise InvalidTaskTransitionError(
                task_id=self.task_id,
                from_status=self.status,
                to_status=new_status,
            )
        event = TaskStatusChanged(
            task_id=self.task_id,
            from_status=self.status,
            to_status=new_status,
        )
        self.status = new_status
        self.pending_events.append(event)
        return event

    def is_active(self) -> bool:
        """Return whether the task is in an actively-executing state."""
        return self.status in ACTIVE_STATUSES

    def is_in_progress(self) -> bool:
        """Return whether the task is still progressing (broader than active)."""
        return self.status in IN_PROGRESS_STATUSES

    def is_terminal(self) -> bool:
        """Return whether the task has reached a terminal state."""
        return not VALID_TRANSITIONS.get(self.status, set())

    def pull_events(self) -> list[TaskStatusChanged]:
        """Drain pending domain events, leaving the aggregate empty."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


__all__ = [
    "InvalidTaskTransitionError",
    "Task",
    "TaskStatusChanged",
]
