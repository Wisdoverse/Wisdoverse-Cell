"""WorkItem aggregate root and status policy.

The Control Plane owns work-item lifecycle vocabulary. Application use
cases should ask this domain module for transition, close-status, and
agent-run mapping decisions instead of duplicating status conditionals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import AgentRunStatus, WorkItemStatus
from ..models import WorkItem as WorkItemRecord
from .events import ControlPlaneDomainEvent
from .state_machine import ControlPlaneStateMachine


class InvalidWorkItemTransitionError(ValueError):
    """Raised when a WorkItem lifecycle transition is not allowed."""


def work_item_status(value: WorkItemStatus | str | None) -> WorkItemStatus | None:
    """Return a typed WorkItemStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, WorkItemStatus):
        return value
    return WorkItemStatus(str(value))


def agent_run_status(value: AgentRunStatus | str | None) -> AgentRunStatus | None:
    """Return a typed AgentRunStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, AgentRunStatus):
        return value
    return AgentRunStatus(str(value))


WORK_ITEM_CLOSE_STATUSES: frozenset[WorkItemStatus] = frozenset(
    {
        WorkItemStatus.COMPLETED,
        WorkItemStatus.FAILED,
        WorkItemStatus.CANCELLED,
    }
)

VALID_TRANSITIONS: dict[WorkItemStatus, frozenset[WorkItemStatus]] = {
    WorkItemStatus.QUEUED: frozenset(
        {
            WorkItemStatus.READY,
            WorkItemStatus.RUNNING,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.AWAITING_APPROVAL,
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.READY: frozenset(
        {
            WorkItemStatus.RUNNING,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.AWAITING_APPROVAL,
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.RUNNING: frozenset(
        {
            WorkItemStatus.BLOCKED,
            WorkItemStatus.AWAITING_APPROVAL,
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.BLOCKED: frozenset(
        {
            WorkItemStatus.READY,
            WorkItemStatus.RUNNING,
            WorkItemStatus.AWAITING_APPROVAL,
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.AWAITING_APPROVAL: frozenset(
        {
            WorkItemStatus.READY,
            WorkItemStatus.RUNNING,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.COMPLETED: frozenset(
        {
            WorkItemStatus.READY,
            WorkItemStatus.RUNNING,
            WorkItemStatus.BLOCKED,
            WorkItemStatus.AWAITING_APPROVAL,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.FAILED: frozenset(
        {
            WorkItemStatus.RUNNING,
            WorkItemStatus.AWAITING_APPROVAL,
            WorkItemStatus.CANCELLED,
        }
    ),
    WorkItemStatus.CANCELLED: frozenset(),
}

STATE_MACHINE = ControlPlaneStateMachine.from_transitions(VALID_TRANSITIONS)


def is_work_item_close_status(status: WorkItemStatus | str) -> bool:
    """True when `status` is valid for the explicit close command."""
    typed_status = work_item_status(status)
    return typed_status in WORK_ITEM_CLOSE_STATUSES


def work_item_status_from_agent_run_status(
    run_status: AgentRunStatus | str | None,
) -> WorkItemStatus:
    """Map an agent-run status to the resulting work-item lifecycle status."""
    status = agent_run_status(run_status)
    if status is None:
        return WorkItemStatus.RUNNING
    if status == AgentRunStatus.SUCCEEDED:
        return WorkItemStatus.COMPLETED
    if status == AgentRunStatus.FAILED:
        return WorkItemStatus.FAILED
    if status == AgentRunStatus.CANCELLED:
        return WorkItemStatus.CANCELLED
    return WorkItemStatus.RUNNING


@dataclass(frozen=True, slots=True)
class WorkItemStatusChanged(ControlPlaneDomainEvent):
    """In-memory domain event raised by WorkItem.transition_to()."""

    work_item_id: str
    company_id: str
    from_status: WorkItemStatus
    to_status: WorkItemStatus


@dataclass
class WorkItem:
    """WorkItem aggregate root for lifecycle transitions."""

    record: WorkItemRecord
    _events: list[WorkItemStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: WorkItemRecord) -> WorkItem:
        return cls(record=record)

    @property
    def work_item_id(self) -> str:
        return self.record.work_item_id

    @property
    def status(self) -> WorkItemStatus:
        status = work_item_status(self.record.status)
        if status is None:
            raise InvalidWorkItemTransitionError(f"WorkItem {self.work_item_id}: missing status")
        return status

    @property
    def is_closed(self) -> bool:
        """True when the work item cannot transition to more work states."""
        return STATE_MACHINE.is_terminal(self.status)

    def transition_to(self, target: WorkItemStatus | str) -> None:
        """Move the aggregate to `target` if permitted by the lifecycle policy."""
        target_status = work_item_status(target)
        if target_status is None:
            raise InvalidWorkItemTransitionError(
                f"WorkItem {self.work_item_id}: missing transition target"
            )
        if target_status == self.status:
            return
        STATE_MACHINE.ensure_can_transition(
            self.status,
            target_status,
            subject=f"WorkItem {self.work_item_id}",
            error_type=InvalidWorkItemTransitionError,
        )
        previous = self.status
        self.record = self.record.model_copy(update={"status": target_status})
        self._events.append(
            WorkItemStatusChanged(
                work_item_id=self.work_item_id,
                company_id=self.record.company_id,
                from_status=previous,
                to_status=target_status,
            )
        )

    def pull_events(self) -> list[WorkItemStatusChanged]:
        """Drain raised domain events for future outbox/audit use."""
        drained = list(self._events)
        self._events.clear()
        return drained


__all__ = [
    "InvalidWorkItemTransitionError",
    "STATE_MACHINE",
    "VALID_TRANSITIONS",
    "WORK_ITEM_CLOSE_STATUSES",
    "WorkItem",
    "WorkItemStatusChanged",
    "agent_run_status",
    "is_work_item_close_status",
    "work_item_status",
    "work_item_status_from_agent_run_status",
]
