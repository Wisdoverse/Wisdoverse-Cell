"""Requirement lifecycle state machine.

Companions `requirement_lifecycle.py` which holds the bare status
constants and the mutation helpers used today. This module adds the
explicit FSM transition table used by the `Requirement` aggregate.

Statuses (already defined in ``requirement_lifecycle``):

- ``pending`` — newly extracted requirement, awaiting confirmation.
- ``confirmed`` — operator or LLM confirmed the requirement.
- ``changed`` — requirement edited after confirmation.
- ``rejected`` — operator rejected the requirement.

Transition rules:

- A pending requirement may be confirmed, rejected, or changed
  (the last covers operator edits before confirmation).
- A confirmed requirement may be edited (``changed``).
- A changed requirement may be re-confirmed or rejected.
- A rejected requirement is terminal.
"""

from __future__ import annotations

from .requirement_lifecycle import CHANGED, CONFIRMED, PENDING, REJECTED

REQUIREMENT_STATUSES: tuple[str, ...] = (PENDING, CONFIRMED, CHANGED, REJECTED)

TERMINAL_STATUSES: tuple[str, ...] = (REJECTED,)

VALID_TRANSITIONS: dict[str, set[str]] = {
    PENDING: {CONFIRMED, REJECTED, CHANGED},
    CONFIRMED: {CHANGED, REJECTED},
    CHANGED: {CONFIRMED, REJECTED},
    REJECTED: set(),
}


def can_transition(from_status: str, to_status: str) -> bool:
    """Return whether a requirement can move between two states."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


def is_terminal(status: str) -> bool:
    """Return whether the given status is a terminal lifecycle state."""
    return status in TERMINAL_STATUSES


__all__ = [
    "REQUIREMENT_STATUSES",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "can_transition",
    "is_terminal",
]
