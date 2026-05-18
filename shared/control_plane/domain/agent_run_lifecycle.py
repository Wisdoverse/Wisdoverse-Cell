"""Agent run lifecycle FSM + aggregate.

Stage 2 (domain modeling) per docs/architecture/migration-plan.md.
Companions the existing application-level helpers under
``shared.control_plane.domain.lifecycle.agent_run_lifecycle`` by
adding the explicit FSM transition table and an
``AgentRunLifecycle`` aggregate.

Statuses (from `shared.control_plane.models.AgentRunStatus`):

- ``pending`` — run record created, not yet started.
- ``running`` — actively executing.
- ``succeeded`` — terminal success.
- ``failed`` — terminal failure (recoverable via a fresh run).
- ``cancelled`` — terminal cancellation.
- ``timed_out`` — terminal timeout.

Transition rules:

- pending -> running | cancelled
- running -> succeeded | failed | cancelled | timed_out
- terminal states are absorbing (no outgoing transitions).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import AgentRunStatus

VALID_TRANSITIONS: dict[AgentRunStatus, set[AgentRunStatus]] = {
    AgentRunStatus.PENDING: {AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED},
    AgentRunStatus.RUNNING: {
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.TIMED_OUT,
    },
    AgentRunStatus.SUCCEEDED: set(),
    AgentRunStatus.FAILED: set(),
    AgentRunStatus.CANCELLED: set(),
    AgentRunStatus.TIMED_OUT: set(),
}

TERMINAL_STATUSES: tuple[AgentRunStatus, ...] = (
    AgentRunStatus.SUCCEEDED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
    AgentRunStatus.TIMED_OUT,
)


def can_transition(from_status: AgentRunStatus, to_status: AgentRunStatus) -> bool:
    """Return whether the lifecycle policy allows this transition."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


def is_terminal(status: AgentRunStatus) -> bool:
    """Return whether the status is terminal."""
    return status in TERMINAL_STATUSES


class InvalidAgentRunTransitionError(Exception):
    """Raised when ``transition_to`` is called with an illegal target."""

    def __init__(
        self,
        *,
        run_id: str,
        from_status: AgentRunStatus,
        to_status: AgentRunStatus,
    ) -> None:
        super().__init__(
            f"illegal agent run transition run_id={run_id} "
            f"{from_status} -> {to_status}"
        )
        self.run_id = run_id
        self.from_status = from_status
        self.to_status = to_status


@dataclass(frozen=True, slots=True)
class AgentRunStatusChanged:
    """Domain event emitted when the aggregate moves between states."""

    run_id: str
    from_status: AgentRunStatus
    to_status: AgentRunStatus


@dataclass(slots=True)
class AgentRunLifecycle:
    """Aggregate for one agent run's lifecycle state.

    Wraps the status field so transitions go through one chokepoint
    instead of being mutated in repository or use-case code.
    """

    run_id: str
    status: AgentRunStatus
    pending_events: list[AgentRunStatusChanged] = field(default_factory=list)

    def transition_to(self, new_status: AgentRunStatus) -> AgentRunStatusChanged:
        """Move the aggregate to ``new_status`` if the policy allows it.

        Raises:
            InvalidAgentRunTransitionError: if the lifecycle policy
                does not allow this transition.
        """
        if not can_transition(self.status, new_status):
            raise InvalidAgentRunTransitionError(
                run_id=self.run_id,
                from_status=self.status,
                to_status=new_status,
            )
        event = AgentRunStatusChanged(
            run_id=self.run_id,
            from_status=self.status,
            to_status=new_status,
        )
        self.status = new_status
        self.pending_events.append(event)
        return event

    def is_terminal(self) -> bool:
        """Return whether the run is in a terminal state."""
        return is_terminal(self.status)

    def pull_events(self) -> list[AgentRunStatusChanged]:
        """Drain pending domain events, leaving the aggregate empty."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


__all__ = [
    "AgentRunLifecycle",
    "AgentRunStatusChanged",
    "InvalidAgentRunTransitionError",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "can_transition",
    "is_terminal",
]
