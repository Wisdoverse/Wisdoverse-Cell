"""Decision aggregate root and lifecycle policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Decision as DecisionRecord
from ..models import DecisionStatus
from .events import ControlPlaneDomainEvent
from .state_machine import ControlPlaneStateMachine


class InvalidDecisionTransitionError(ValueError):
    """Raised when a Decision status transition is not allowed."""


def decision_status(value: DecisionStatus | str | None) -> DecisionStatus | None:
    """Return a typed DecisionStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, DecisionStatus):
        return value
    return DecisionStatus(str(value))


VALID_TRANSITIONS: dict[DecisionStatus, frozenset[DecisionStatus]] = {
    DecisionStatus.PROPOSED: frozenset(
        {
            DecisionStatus.ACCEPTED,
            DecisionStatus.REJECTED,
            DecisionStatus.SUPERSEDED,
        }
    ),
    DecisionStatus.ACCEPTED: frozenset({DecisionStatus.SUPERSEDED}),
    DecisionStatus.REJECTED: frozenset({DecisionStatus.SUPERSEDED}),
    DecisionStatus.SUPERSEDED: frozenset(),
}

STATE_MACHINE = ControlPlaneStateMachine.from_transitions(VALID_TRANSITIONS)

TERMINAL_STATUSES: frozenset[DecisionStatus] = STATE_MACHINE.terminal_states


@dataclass(frozen=True, slots=True)
class DecisionStatusChanged(ControlPlaneDomainEvent):
    """In-memory domain event raised by Decision.transition_to()."""

    decision_id: str
    company_id: str
    from_status: DecisionStatus
    to_status: DecisionStatus


@dataclass
class Decision:
    """Decision aggregate root for operator decision lifecycle."""

    record: DecisionRecord
    _events: list[DecisionStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: DecisionRecord) -> Decision:
        return cls(record=record)

    @property
    def decision_id(self) -> str:
        return self.record.decision_id

    @property
    def status(self) -> DecisionStatus:
        status = decision_status(self.record.status)
        if status is None:
            raise InvalidDecisionTransitionError(f"Decision {self.decision_id}: missing status")
        return status

    @property
    def is_terminal(self) -> bool:
        """True when no further decision lifecycle transition is allowed."""
        return STATE_MACHINE.is_terminal(self.status)

    def transition_to(self, target: DecisionStatus | str) -> None:
        """Move the decision to `target` if permitted by the lifecycle policy."""
        target_status = decision_status(target)
        if target_status is None:
            raise InvalidDecisionTransitionError(
                f"Decision {self.decision_id}: missing transition target"
            )
        if target_status == self.status:
            return
        STATE_MACHINE.ensure_can_transition(
            self.status,
            target_status,
            subject=f"Decision {self.decision_id}",
            error_type=InvalidDecisionTransitionError,
        )
        previous = self.status
        self.record = self.record.model_copy(update={"status": target_status})
        self._events.append(
            DecisionStatusChanged(
                decision_id=self.decision_id,
                company_id=self.record.company_id,
                from_status=previous,
                to_status=target_status,
            )
        )

    def pull_events(self) -> list[DecisionStatusChanged]:
        """Drain raised domain events for future outbox/audit use."""
        drained = list(self._events)
        self._events.clear()
        return drained


__all__ = [
    "Decision",
    "DecisionStatusChanged",
    "InvalidDecisionTransitionError",
    "STATE_MACHINE",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "decision_status",
]
