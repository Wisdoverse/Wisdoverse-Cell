"""ApprovalRequest aggregate root and lifecycle policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import ApprovalRequest as ApprovalRequestRecord
from ..models import ApprovalStatus
from .events import ControlPlaneDomainEvent
from .state_machine import ControlPlaneStateMachine


class InvalidApprovalTransitionError(ValueError):
    """Raised when an ApprovalRequest lifecycle transition is not allowed."""


def approval_status(value: ApprovalStatus | str | None) -> ApprovalStatus | None:
    """Return a typed ApprovalStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, ApprovalStatus):
        return value
    return ApprovalStatus(str(value))


VALID_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    ),
    ApprovalStatus.APPROVED: frozenset(),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.EXPIRED: frozenset(),
    ApprovalStatus.CANCELLED: frozenset(),
}

STATE_MACHINE = ControlPlaneStateMachine.from_transitions(VALID_TRANSITIONS)

TERMINAL_STATUSES: frozenset[ApprovalStatus] = STATE_MACHINE.terminal_states


def approval_status_is_approved(status: ApprovalStatus | str | None) -> bool:
    """True when the approval status grants permission for sensitive work."""
    return approval_status(status) == ApprovalStatus.APPROVED


@dataclass(frozen=True, slots=True)
class ApprovalStatusChanged(ControlPlaneDomainEvent):
    """In-memory domain event raised by ApprovalRequest.transition_to()."""

    approval_id: str
    company_id: str
    from_status: ApprovalStatus
    to_status: ApprovalStatus


@dataclass
class ApprovalRequest:
    """ApprovalRequest aggregate root for human-in-the-loop decisions."""

    record: ApprovalRequestRecord
    _events: list[ApprovalStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: ApprovalRequestRecord) -> ApprovalRequest:
        return cls(record=record)

    @property
    def approval_id(self) -> str:
        return self.record.approval_id

    @property
    def status(self) -> ApprovalStatus:
        status = approval_status(self.record.status)
        if status is None:
            raise InvalidApprovalTransitionError(
                f"ApprovalRequest {self.approval_id}: missing status"
            )
        return status

    @property
    def is_approved(self) -> bool:
        """True when the approval grants permission for sensitive work."""
        return approval_status_is_approved(self.status)

    @property
    def is_terminal(self) -> bool:
        """True when no further approval lifecycle transition is allowed."""
        return STATE_MACHINE.is_terminal(self.status)

    def transition_to(self, target: ApprovalStatus | str) -> None:
        """Move the approval request to `target` if permitted by policy."""
        target_status = approval_status(target)
        if target_status is None:
            raise InvalidApprovalTransitionError(
                f"ApprovalRequest {self.approval_id}: missing transition target"
            )
        if target_status == self.status:
            return
        STATE_MACHINE.ensure_can_transition(
            self.status,
            target_status,
            subject=f"ApprovalRequest {self.approval_id}",
            error_type=InvalidApprovalTransitionError,
        )
        previous = self.status
        self.record = self.record.model_copy(update={"status": target_status})
        self._events.append(
            ApprovalStatusChanged(
                approval_id=self.approval_id,
                company_id=self.record.company_id,
                from_status=previous,
                to_status=target_status,
            )
        )

    def pull_events(self) -> list[ApprovalStatusChanged]:
        """Drain raised domain events for future outbox/audit use."""
        drained = list(self._events)
        self._events.clear()
        return drained


__all__ = [
    "ApprovalRequest",
    "ApprovalStatusChanged",
    "InvalidApprovalTransitionError",
    "STATE_MACHINE",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "approval_status",
    "approval_status_is_approved",
]
