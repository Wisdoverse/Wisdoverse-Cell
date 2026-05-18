"""Dev task lifecycle policy.

This module owns the domain-level state machine for delivery tasks. Persistence
adapters call these functions instead of carrying transition rules themselves.
"""

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"planning", "expired", "failed"},
    "planning": {"awaiting_approval", "executing", "failed"},
    "awaiting_approval": {"executing", "failed"},
    "executing": {"security_scanning", "failed"},
    "security_scanning": {"mr_creating", "failed"},
    "mr_creating": {"mr_created", "failed"},
    "mr_created": {"qa_triggered", "failed"},
    "qa_triggered": {"reviewing", "failed"},
    "reviewing": {"completed", "failed"},
    "completed": set(),
    "failed": {"planning"},
    "expired": set(),
}

ACTIVE_STATUSES: tuple[str, ...] = (
    "executing",
    "security_scanning",
    "mr_creating",
    "mr_created",
    "qa_triggered",
    "reviewing",
)

IN_PROGRESS_STATUSES: tuple[str, ...] = (
    "planning",
    "awaiting_approval",
    *ACTIVE_STATUSES,
)


def can_transition(from_status: str, to_status: str) -> bool:
    """Return whether a delivery task can move between two lifecycle states."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


__all__ = [
    "ACTIVE_STATUSES",
    "IN_PROGRESS_STATUSES",
    "VALID_TRANSITIONS",
    "can_transition",
]
