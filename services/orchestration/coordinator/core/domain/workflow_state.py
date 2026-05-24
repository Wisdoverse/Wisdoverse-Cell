"""Workflow-state aggregate for Coordinator orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class InvalidCoordinatorWorkflowError(ValueError):
    """Raised when workflow state violates Coordinator invariants."""


class InvalidCoordinatorWorkflowTransitionError(ValueError):
    """Raised when workflow status transition is invalid."""


class CoordinatorWorkflowStatus(StrEnum):
    """Lifecycle states for a Coordinator workflow."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[CoordinatorWorkflowStatus, set[CoordinatorWorkflowStatus]] = {
    CoordinatorWorkflowStatus.ACTIVE: {
        CoordinatorWorkflowStatus.PAUSED,
        CoordinatorWorkflowStatus.COMPLETED,
        CoordinatorWorkflowStatus.FAILED,
    },
    CoordinatorWorkflowStatus.PAUSED: {
        CoordinatorWorkflowStatus.ACTIVE,
        CoordinatorWorkflowStatus.FAILED,
    },
    CoordinatorWorkflowStatus.COMPLETED: set(),
    CoordinatorWorkflowStatus.FAILED: set(),
}


class WorkflowStateLike(Protocol):
    """Record shape consumed by the Coordinator workflow aggregate."""

    workflow_id: str
    type: str
    status: str
    current_phase: str
    agents_involved: list[str]
    created_at: datetime
    updated_at: datetime
    context: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CoordinatorWorkflowStatusChanged:
    """In-memory event raised when a workflow status changes."""

    workflow_id: str
    previous_status: CoordinatorWorkflowStatus
    status: CoordinatorWorkflowStatus
    occurred_at: datetime

    @property
    def event_name(self) -> str:
        """Return the stable class-name event identifier."""
        return type(self).__name__

    def to_payload(self) -> dict[str, Any]:
        """Return primitive event data for future outbox/audit adapters."""
        return {
            "workflow_id": self.workflow_id,
            "previous_status": self.previous_status.value,
            "status": self.status.value,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class CoordinatorWorkflowState:
    """Aggregate root for one Coordinator workflow state row."""

    workflow_id: str
    workflow_type: str
    status: CoordinatorWorkflowStatus
    current_phase: str
    agents_involved: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    context: dict[str, Any] = field(default_factory=dict)
    _events: list[CoordinatorWorkflowStatusChanged] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        workflow_id: str,
        workflow_type: str,
        current_phase: str,
        agents_involved: list[str] | tuple[str, ...],
        context: dict[str, Any] | None = None,
        status: CoordinatorWorkflowStatus = CoordinatorWorkflowStatus.ACTIVE,
        created_at: datetime | None = None,
    ) -> "CoordinatorWorkflowState":
        """Create a valid workflow aggregate."""
        now = datetime.now(UTC)
        state = cls(
            workflow_id=_require_text(workflow_id, "workflow_id"),
            workflow_type=_require_text(workflow_type, "workflow_type"),
            status=status,
            current_phase=_require_text(current_phase, "current_phase"),
            agents_involved=_normalize_agents(agents_involved),
            created_at=created_at or now,
            updated_at=now,
            context=dict(context or {}),
        )
        state._validate()
        return state

    @classmethod
    def from_record(cls, record: WorkflowStateLike) -> "CoordinatorWorkflowState":
        """Hydrate a workflow aggregate from a persisted record."""
        state = cls(
            workflow_id=_require_text(record.workflow_id, "workflow_id"),
            workflow_type=_require_text(record.type, "workflow_type"),
            status=CoordinatorWorkflowStatus(record.status),
            current_phase=_require_text(record.current_phase, "current_phase"),
            agents_involved=_normalize_agents(record.agents_involved),
            created_at=record.created_at,
            updated_at=record.updated_at,
            context=dict(record.context or {}),
        )
        state._validate()
        return state

    def transition_to(
        self,
        status: CoordinatorWorkflowStatus,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        """Move the workflow through a valid lifecycle transition."""
        if status == self.status:
            return
        if status not in _VALID_TRANSITIONS[self.status]:
            raise InvalidCoordinatorWorkflowTransitionError(
                f"cannot transition coordinator workflow {self.workflow_id} "
                f"from {self.status.value} to {status.value}"
            )
        previous = self.status
        timestamp = occurred_at or datetime.now(UTC)
        self.status = status
        self.updated_at = timestamp
        self._events.append(
            CoordinatorWorkflowStatusChanged(
                workflow_id=self.workflow_id,
                previous_status=previous,
                status=status,
                occurred_at=timestamp,
            )
        )

    def add_agent(self, agent_id: str) -> None:
        """Record that an agent participates in this workflow."""
        normalized = _require_text(agent_id, "agent_id")
        if normalized in self.agents_involved:
            return
        self.agents_involved = (*self.agents_involved, normalized)
        self.updated_at = datetime.now(UTC)

    def advance_phase(self, phase: str) -> None:
        """Move to a new non-empty workflow phase."""
        normalized = _require_text(phase, "current_phase")
        if normalized == self.current_phase:
            return
        self.current_phase = normalized
        self.updated_at = datetime.now(UTC)

    def to_record_kwargs(self) -> dict[str, Any]:
        """Return primitive fields compatible with Coordinator state records."""
        self._validate()
        return {
            "workflow_id": self.workflow_id,
            "type": self.workflow_type,
            "status": self.status.value,
            "current_phase": self.current_phase,
            "agents_involved": list(self.agents_involved),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context": dict(self.context),
        }

    def pull_events(self) -> list[CoordinatorWorkflowStatusChanged]:
        """Drain aggregate-raised workflow events."""
        events = list(self._events)
        self._events.clear()
        return events

    def _validate(self) -> None:
        if self.updated_at < self.created_at:
            raise InvalidCoordinatorWorkflowError("updated_at cannot precede created_at")
        if len(set(self.agents_involved)) != len(self.agents_involved):
            raise InvalidCoordinatorWorkflowError("agents_involved must be unique")
        if not self.agents_involved:
            raise InvalidCoordinatorWorkflowError("workflow must involve at least one agent")


def _normalize_agents(agents: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(_require_text(agent, "agent_id") for agent in agents)
    if len(set(normalized)) != len(normalized):
        raise InvalidCoordinatorWorkflowError("agents_involved must be unique")
    return normalized


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise InvalidCoordinatorWorkflowError(f"{field_name} must not be empty")
    return normalized


__all__ = [
    "CoordinatorWorkflowState",
    "CoordinatorWorkflowStatus",
    "CoordinatorWorkflowStatusChanged",
    "InvalidCoordinatorWorkflowError",
    "InvalidCoordinatorWorkflowTransitionError",
]
