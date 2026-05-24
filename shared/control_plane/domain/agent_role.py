"""AgentRole aggregate root and runtime-status policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..models import AgentRole as AgentRoleRecord
from .events import ControlPlaneDomainEvent
from .state_machine import ControlPlaneStateMachine


class AgentRoleStatus(StrEnum):
    """Published Control Plane status vocabulary for durable AgentRole records."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    INACTIVE = "inactive"
    RETIRED = "retired"
    TERMINATED = "terminated"


class InvalidAgentRoleStatusError(ValueError):
    """Raised when an AgentRole status is outside the published vocabulary."""


class InvalidAgentRoleTransitionError(ValueError):
    """Raised when an AgentRole status transition is not allowed."""


def agent_role_status(value: AgentRoleStatus | str | None) -> AgentRoleStatus | None:
    """Return a typed AgentRoleStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, AgentRoleStatus):
        return value
    try:
        return AgentRoleStatus(str(value).strip().lower())
    except ValueError as exc:
        raise InvalidAgentRoleStatusError(str(value)) from exc


VALID_TRANSITIONS: dict[AgentRoleStatus, frozenset[AgentRoleStatus]] = {
    AgentRoleStatus.ACTIVE: frozenset(
        {
            AgentRoleStatus.PAUSED,
            AgentRoleStatus.DISABLED,
            AgentRoleStatus.INACTIVE,
            AgentRoleStatus.RETIRED,
            AgentRoleStatus.TERMINATED,
        }
    ),
    AgentRoleStatus.PAUSED: frozenset(
        {
            AgentRoleStatus.ACTIVE,
            AgentRoleStatus.DISABLED,
            AgentRoleStatus.INACTIVE,
            AgentRoleStatus.RETIRED,
            AgentRoleStatus.TERMINATED,
        }
    ),
    AgentRoleStatus.DISABLED: frozenset(
        {
            AgentRoleStatus.ACTIVE,
            AgentRoleStatus.INACTIVE,
            AgentRoleStatus.RETIRED,
            AgentRoleStatus.TERMINATED,
        }
    ),
    AgentRoleStatus.INACTIVE: frozenset(
        {
            AgentRoleStatus.ACTIVE,
            AgentRoleStatus.DISABLED,
            AgentRoleStatus.RETIRED,
            AgentRoleStatus.TERMINATED,
        }
    ),
    AgentRoleStatus.RETIRED: frozenset(),
    AgentRoleStatus.TERMINATED: frozenset(),
}

RUNNABLE_STATUSES: frozenset[AgentRoleStatus] = frozenset({AgentRoleStatus.ACTIVE})

STATE_MACHINE = ControlPlaneStateMachine.from_transitions(VALID_TRANSITIONS)

TERMINAL_STATUSES: frozenset[AgentRoleStatus] = STATE_MACHINE.terminal_states


@dataclass(frozen=True, slots=True)
class AgentRoleStatusChanged(ControlPlaneDomainEvent):
    """In-memory domain event raised by AgentRole.transition_to()."""

    role_id: str
    agent_id: str
    company_id: str
    from_status: AgentRoleStatus
    to_status: AgentRoleStatus


@dataclass
class AgentRole:
    """AgentRole aggregate root for durable role lifecycle and runnability."""

    record: AgentRoleRecord
    _events: list[AgentRoleStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: AgentRoleRecord) -> AgentRole:
        return cls(record=record)

    @property
    def role_id(self) -> str:
        return self.record.role_id

    @property
    def agent_id(self) -> str:
        return self.record.agent_id

    @property
    def status(self) -> AgentRoleStatus:
        status = agent_role_status(self.record.status)
        if status is None:
            raise InvalidAgentRoleStatusError(f"AgentRole {self.agent_id}: missing status")
        return status

    @property
    def is_runnable(self) -> bool:
        """True when the role is eligible for wakeup execution."""
        return self.status in RUNNABLE_STATUSES

    @property
    def is_terminal(self) -> bool:
        """True when the role cannot transition further."""
        return STATE_MACHINE.is_terminal(self.status)

    def transition_to(self, target: AgentRoleStatus | str) -> None:
        """Move the role to `target` if permitted by the lifecycle policy."""
        target_status = agent_role_status(target)
        if target_status is None:
            raise InvalidAgentRoleStatusError(
                f"AgentRole {self.agent_id}: missing transition target"
            )
        if target_status == self.status:
            return
        STATE_MACHINE.ensure_can_transition(
            self.status,
            target_status,
            subject=f"AgentRole {self.agent_id}",
            error_type=InvalidAgentRoleTransitionError,
        )
        previous = self.status
        self.record = self.record.model_copy(update={"status": target_status.value})
        self._events.append(
            AgentRoleStatusChanged(
                role_id=self.role_id,
                agent_id=self.agent_id,
                company_id=self.record.company_id,
                from_status=previous,
                to_status=target_status,
            )
        )

    def pull_events(self) -> list[AgentRoleStatusChanged]:
        """Drain raised domain events for audit/outbox collection."""
        drained = list(self._events)
        self._events.clear()
        return drained


__all__ = [
    "AgentRole",
    "AgentRoleStatus",
    "AgentRoleStatusChanged",
    "InvalidAgentRoleStatusError",
    "InvalidAgentRoleTransitionError",
    "RUNNABLE_STATUSES",
    "STATE_MACHINE",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "agent_role_status",
]
