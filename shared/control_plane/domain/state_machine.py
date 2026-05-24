"""Control Plane state-machine value object."""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, TypeVar

StateT = TypeVar("StateT", bound=Hashable)


class InvalidControlPlaneStateMachineError(ValueError):
    """Raised when a Control Plane state-machine definition is invalid."""


@dataclass(frozen=True, slots=True)
class ControlPlaneStateMachine(Generic[StateT]):
    """Immutable transition table for Control Plane aggregate lifecycles."""

    transitions: Mapping[StateT, frozenset[StateT]]

    def __post_init__(self) -> None:
        normalized = {
            state: frozenset(targets)
            for state, targets in dict(self.transitions).items()
        }
        missing_targets = {
            target
            for targets in normalized.values()
            for target in targets
            if target not in normalized
        }
        if missing_targets:
            missing = ", ".join(str(target) for target in sorted(missing_targets, key=str))
            raise InvalidControlPlaneStateMachineError(f"missing_transition_rows:{missing}")
        object.__setattr__(self, "transitions", MappingProxyType(normalized))

    @classmethod
    def from_transitions(
        cls,
        transitions: Mapping[StateT, Iterable[StateT]],
    ) -> ControlPlaneStateMachine[StateT]:
        return cls(
            {
                state: frozenset(targets)
                for state, targets in transitions.items()
            }
        )

    @property
    def terminal_states(self) -> frozenset[StateT]:
        return frozenset(
            state for state, targets in self.transitions.items() if not targets
        )

    def allowed_targets(self, current: StateT) -> frozenset[StateT]:
        try:
            return self.transitions[current]
        except KeyError as exc:
            raise InvalidControlPlaneStateMachineError(
                f"unknown_current_state:{current}"
            ) from exc

    def can_transition(self, current: StateT, target: StateT) -> bool:
        return target in self.allowed_targets(current)

    def is_terminal(self, state: StateT) -> bool:
        return not self.allowed_targets(state)

    def ensure_can_transition(
        self,
        current: StateT,
        target: StateT,
        *,
        subject: str,
        error_type: type[ValueError],
        transition_name: str = "transition",
    ) -> None:
        if self.can_transition(current, target):
            return
        raise error_type(
            f"{subject}: illegal {transition_name} {current} -> {target}"
        )


__all__ = [
    "ControlPlaneStateMachine",
    "InvalidControlPlaneStateMachineError",
]
