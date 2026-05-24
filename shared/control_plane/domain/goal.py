"""Goal aggregate root and lifecycle policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Goal as GoalRecord
from ..models import GoalStatus
from .events import ControlPlaneDomainEvent
from .state_machine import ControlPlaneStateMachine


class InvalidGoalTransitionError(ValueError):
    """Raised when a Goal status transition is not allowed."""


def goal_status(value: GoalStatus | str | None) -> GoalStatus | None:
    """Return a typed GoalStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, GoalStatus):
        return value
    return GoalStatus(str(value))


VALID_TRANSITIONS: dict[GoalStatus, frozenset[GoalStatus]] = {
    GoalStatus.DRAFT: frozenset(
        {
            GoalStatus.ACTIVE,
            GoalStatus.PAUSED,
            GoalStatus.COMPLETED,
            GoalStatus.CANCELLED,
        }
    ),
    GoalStatus.ACTIVE: frozenset(
        {
            GoalStatus.PAUSED,
            GoalStatus.COMPLETED,
            GoalStatus.CANCELLED,
        }
    ),
    GoalStatus.PAUSED: frozenset(
        {
            GoalStatus.ACTIVE,
            GoalStatus.COMPLETED,
            GoalStatus.CANCELLED,
        }
    ),
    GoalStatus.COMPLETED: frozenset(
        {
            GoalStatus.ACTIVE,
            GoalStatus.PAUSED,
            GoalStatus.CANCELLED,
        }
    ),
    GoalStatus.CANCELLED: frozenset(),
}

STATE_MACHINE = ControlPlaneStateMachine.from_transitions(VALID_TRANSITIONS)

TERMINAL_STATUSES: frozenset[GoalStatus] = STATE_MACHINE.terminal_states


def goal_current_value_for_transition(
    *,
    target_status: GoalStatus | str,
    explicit_current_value: float | None,
    target_value: float | None,
) -> float | None:
    """Return the progress value to persist for a goal status transition.

    `None` means "do not change the persisted current value"; the store uses
    that sentinel already, so the domain helper keeps that behavior explicit.
    """
    if explicit_current_value is not None:
        return explicit_current_value
    if goal_status(target_status) == GoalStatus.COMPLETED and target_value is not None:
        return target_value
    return None


@dataclass(frozen=True, slots=True)
class GoalStatusChanged(ControlPlaneDomainEvent):
    """In-memory domain event raised by Goal.transition_to()."""

    goal_id: str
    company_id: str
    from_status: GoalStatus
    to_status: GoalStatus


@dataclass
class Goal:
    """Goal aggregate root for operator objective lifecycle."""

    record: GoalRecord
    _events: list[GoalStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: GoalRecord) -> Goal:
        return cls(record=record)

    @property
    def goal_id(self) -> str:
        return self.record.goal_id

    @property
    def status(self) -> GoalStatus:
        status = goal_status(self.record.status)
        if status is None:
            raise InvalidGoalTransitionError(f"Goal {self.goal_id}: missing status")
        return status

    @property
    def is_terminal(self) -> bool:
        """True when no further goal lifecycle transition is allowed."""
        return STATE_MACHINE.is_terminal(self.status)

    def transition_to(self, target: GoalStatus | str) -> None:
        """Move the aggregate to `target` if permitted by the lifecycle policy."""
        target_status = goal_status(target)
        if target_status is None:
            raise InvalidGoalTransitionError(f"Goal {self.goal_id}: missing transition target")
        if target_status == self.status:
            return
        STATE_MACHINE.ensure_can_transition(
            self.status,
            target_status,
            subject=f"Goal {self.goal_id}",
            error_type=InvalidGoalTransitionError,
        )
        previous = self.status
        self.record = self.record.model_copy(update={"status": target_status})
        self._events.append(
            GoalStatusChanged(
                goal_id=self.goal_id,
                company_id=self.record.company_id,
                from_status=previous,
                to_status=target_status,
            )
        )

    def current_value_for_update(self, explicit_current_value: float | None) -> float | None:
        """Return the progress value to pass to the persistence port."""
        return goal_current_value_for_transition(
            target_status=self.status,
            explicit_current_value=explicit_current_value,
            target_value=self.record.target_value,
        )

    def pull_events(self) -> list[GoalStatusChanged]:
        """Drain raised domain events for future outbox/audit use."""
        drained = list(self._events)
        self._events.clear()
        return drained


__all__ = [
    "Goal",
    "GoalStatusChanged",
    "InvalidGoalTransitionError",
    "STATE_MACHINE",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "goal_current_value_for_transition",
    "goal_status",
]
