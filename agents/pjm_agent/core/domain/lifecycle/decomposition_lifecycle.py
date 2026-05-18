"""Decomposition lifecycle policy.

Extracted from string literals in
``agents.pjm_agent.core.decomposition_orchestrator`` and
``agents.pjm_agent.db.repository``. Persistence adapters and use cases
should consume the constants and ``can_transition`` helper from this
module instead of repeating string literals.

Status meanings:

- ``pending`` — decomposition record created; awaits write or rejection.
- ``writing`` — write to OpenProject in progress.
- ``approved`` — decomposition accepted (write succeeded, or no write
  needed).
- ``write_failed`` — write to OpenProject failed but the decomposition
  state itself is recoverable on retry.
- ``failed`` — terminal failure (e.g., LLM error during decomposition).
- ``rejected`` — operator or LLM rejected the decomposition.

The transition table reflects the observable behavior in the
decomposition orchestrator as of Migration Plan §Stage 1. It is
deliberately conservative: cycles back to ``pending`` are not allowed,
and terminal states (``approved``, ``rejected``, ``failed``) do not
re-enter the lifecycle without a fresh record.
"""

PENDING = "pending"
WRITING = "writing"
APPROVED = "approved"
WRITE_FAILED = "write_failed"
FAILED = "failed"
REJECTED = "rejected"

DECOMPOSITION_STATUSES: tuple[str, ...] = (
    PENDING,
    WRITING,
    APPROVED,
    WRITE_FAILED,
    FAILED,
    REJECTED,
)

TERMINAL_STATUSES: tuple[str, ...] = (APPROVED, REJECTED, FAILED)

VALID_TRANSITIONS: dict[str, set[str]] = {
    PENDING: {WRITING, APPROVED, FAILED, REJECTED, WRITE_FAILED},
    WRITING: {APPROVED, WRITE_FAILED, FAILED},
    WRITE_FAILED: {WRITING, FAILED, REJECTED},
    APPROVED: set(),
    REJECTED: set(),
    FAILED: set(),
}


def can_transition(from_status: str, to_status: str) -> bool:
    """Return whether a decomposition record can move between two states."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


def is_terminal(status: str) -> bool:
    """Return whether the given status is a terminal lifecycle state."""
    return status in TERMINAL_STATUSES


__all__ = [
    "APPROVED",
    "DECOMPOSITION_STATUSES",
    "FAILED",
    "PENDING",
    "REJECTED",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "WRITE_FAILED",
    "WRITING",
    "can_transition",
    "is_terminal",
]
