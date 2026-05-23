"""EvolutionProposal aggregate root (DDD-005 seed).

Seeds the explicit aggregate-class pattern for `EvolutionProposal`
per `architecture-principles.md` §1 Domain layer + §4.8
(Aggregate-Raised Domain Events) + §4.10 (State Machines), and
audit row DDD-005.

The Control Plane today carries `EvolutionProposal` as an anemic
Pydantic record in `shared/control_plane/models.py`; the rollout
state machine is implicit (string comparisons in
`evolution_proposal_use_cases.py`). This module wraps the record
in an aggregate class that owns the rollout FSM and raises typed
in-memory domain events.

Approval state remains on the underlying record; the
`approval_state` field is governed by the existing approval-gate
domain service in `shared/control_plane/approval_gate.py`. This
aggregate owns the **rollout** state machine, which Vernon-style
encapsulates the safe progression from proposed → shadow → canary
→ active.

Rollout transitions:

- proposed → shadow, canary, rejected
- shadow → canary, rolled_back
- canary → active, rolled_back
- active → rolled_back
- rolled_back → (terminal)
- rejected → (terminal)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import EvolutionProposal as EvolutionProposalRecord
from ..models import EvolutionRolloutState


class InvalidEvolutionRolloutTransitionError(ValueError):
    """Raised when an EvolutionProposal rollout transition is not allowed."""


VALID_ROLLOUT_TRANSITIONS: dict[
    EvolutionRolloutState, frozenset[EvolutionRolloutState]
] = {
    EvolutionRolloutState.PROPOSED: frozenset(
        {
            EvolutionRolloutState.SHADOW,
            EvolutionRolloutState.CANARY,
            EvolutionRolloutState.REJECTED,
        }
    ),
    EvolutionRolloutState.SHADOW: frozenset(
        {
            EvolutionRolloutState.CANARY,
            EvolutionRolloutState.ROLLED_BACK,
        }
    ),
    EvolutionRolloutState.CANARY: frozenset(
        {
            EvolutionRolloutState.ACTIVE,
            EvolutionRolloutState.ROLLED_BACK,
        }
    ),
    EvolutionRolloutState.ACTIVE: frozenset(
        {EvolutionRolloutState.ROLLED_BACK}
    ),
    EvolutionRolloutState.ROLLED_BACK: frozenset(),
    EvolutionRolloutState.REJECTED: frozenset(),
}


TERMINAL_ROLLOUT_STATES: frozenset[EvolutionRolloutState] = frozenset(
    state for state, allowed in VALID_ROLLOUT_TRANSITIONS.items() if not allowed
)


@dataclass(frozen=True, slots=True)
class EvolutionRolloutStatusChanged:
    """In-memory domain event raised by EvolutionProposal.advance_rollout()."""

    proposal_id: str
    company_id: str
    from_state: EvolutionRolloutState
    to_state: EvolutionRolloutState


@dataclass
class EvolutionProposal:
    """EvolutionProposal aggregate root.

    Wraps the persistence record and owns the rollout FSM. Construct
    via `EvolutionProposal.from_record(record)`; drain raised events
    via `pull_events()` after each transition so the use case can
    write them to the outbox in the same transaction.
    """

    record: EvolutionProposalRecord
    _events: list[EvolutionRolloutStatusChanged] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: EvolutionProposalRecord) -> EvolutionProposal:
        return cls(record=record)

    @property
    def proposal_id(self) -> str:
        return self.record.proposal_id

    @property
    def rollout_state(self) -> EvolutionRolloutState:
        return self.record.rollout_state

    @property
    def is_terminal(self) -> bool:
        return self.rollout_state in TERMINAL_ROLLOUT_STATES

    def advance_rollout(self, target: EvolutionRolloutState) -> None:
        """Move rollout state to `target` if permitted by the FSM."""
        if target not in VALID_ROLLOUT_TRANSITIONS[self.rollout_state]:
            raise InvalidEvolutionRolloutTransitionError(
                f"EvolutionProposal {self.proposal_id}: illegal rollout "
                f"transition {self.rollout_state} -> {target}"
            )
        previous = self.rollout_state
        self.record = self.record.model_copy(update={"rollout_state": target})
        self._events.append(
            EvolutionRolloutStatusChanged(
                proposal_id=self.proposal_id,
                company_id=self.record.company_id,
                from_state=previous,
                to_state=target,
            )
        )

    def pull_events(self) -> list[EvolutionRolloutStatusChanged]:
        """Drain raised domain events for outbox forwarding."""
        drained = list(self._events)
        self._events.clear()
        return drained
