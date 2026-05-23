"""AgentRun aggregate root (DDD-001 seed).

Seeds the explicit aggregate-class pattern for `AgentRun` per
``architecture-principles.md`` §1 Domain layer and §4.8
(Aggregate-Raised Domain Events) and audit row DDD-001.

The Control Plane today carries `AgentRun` as an anemic Pydantic
record in ``shared/control_plane/models.py``; state-transition decisions
live in ``shared/control_plane/domain/lifecycle/agent_run_lifecycle.py``
as free functions. This module wraps the record in an aggregate class
that owns the state machine and raises typed in-memory domain events.

This is a **seed** PR: the aggregate class lives alongside the existing
free-function helpers; use-case migration to consume the aggregate
follows in dedicated per-use-case PRs so each migration stays
reviewable per ``architecture-principles.md`` §3 ("no mass file moves").

The legacy shim at ``shared/control_plane/agent_run_lifecycle.py``
has been removed; all callers import directly from
``shared/control_plane/domain/lifecycle/agent_run_lifecycle.py``.
The remaining DDD-001 follow-up:

- ``tests/unit/test_architecture_boundaries.py::test_lifecycle_modules_live_in_canonical_domain_path``
  is extended to require this canonical location for the Control Plane.
- The free helpers in
  ``shared/control_plane/domain/lifecycle/agent_run_lifecycle.py``
  are reduced to thin adapters or absorbed into the aggregate once
  every use case that mutates AgentRun consumes this aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import AgentRun as AgentRunRecord
from ..models import AgentRunStatus


class InvalidAgentRunTransitionError(ValueError):
    """Raised when an AgentRun state transition is not allowed by the FSM."""


VALID_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.PENDING: frozenset(
        {AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED, AgentRunStatus.FAILED}
    ),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
    AgentRunStatus.SUCCEEDED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
    AgentRunStatus.CANCELLED: frozenset(),
    AgentRunStatus.TIMED_OUT: frozenset(),
}


TERMINAL_STATUSES: frozenset[AgentRunStatus] = frozenset(
    status for status, allowed in VALID_TRANSITIONS.items() if not allowed
)


@dataclass(frozen=True, slots=True)
class AgentRunStatusChanged:
    """In-memory domain event raised by AgentRun.transition_to()."""

    run_id: str
    agent_id: str
    company_id: str
    from_status: AgentRunStatus
    to_status: AgentRunStatus


@dataclass
class AgentRun:
    """AgentRun aggregate root.

    Wraps the persistence record (`AgentRunRecord`) and owns the
    state-machine invariants. Construct from a record via
    ``AgentRun.from_record(record)``; drain raised events via
    ``pull_events()`` after each transition so the use case can write
    them to the outbox in the same transaction.
    """

    record: AgentRunRecord
    _events: list[AgentRunStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: AgentRunRecord) -> AgentRun:
        return cls(record=record)

    @property
    def status(self) -> AgentRunStatus:
        return self.record.status

    @property
    def run_id(self) -> str:
        return self.record.run_id

    @property
    def is_terminal(self) -> bool:
        """True when the aggregate cannot transition further."""
        return not VALID_TRANSITIONS[self.status]

    def transition_to(self, target: AgentRunStatus) -> None:
        """Move the aggregate to a new status if permitted by the FSM."""
        if target not in VALID_TRANSITIONS[self.status]:
            raise InvalidAgentRunTransitionError(
                f"AgentRun {self.run_id}: illegal transition "
                f"{self.status} -> {target}"
            )
        previous = self.status
        self.record = self.record.model_copy(update={"status": target})
        self._events.append(
            AgentRunStatusChanged(
                run_id=self.run_id,
                agent_id=self.record.agent_id,
                company_id=self.record.company_id,
                from_status=previous,
                to_status=target,
            )
        )

    def pull_events(self) -> list[AgentRunStatusChanged]:
        """Drain raised domain events. Use case forwards them to the outbox."""
        drained = list(self._events)
        self._events.clear()
        return drained
