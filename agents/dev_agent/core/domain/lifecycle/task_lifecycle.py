"""Dev task lifecycle policy.

This module owns the domain-level state machine for delivery tasks. Persistence
adapters call these functions instead of carrying transition rules themselves.
"""

PENDING = "pending"
PLANNING = "planning"
AWAITING_APPROVAL = "awaiting_approval"
EXECUTING = "executing"
SECURITY_SCANNING = "security_scanning"
MR_CREATING = "mr_creating"
MR_CREATED = "mr_created"
QA_TRIGGERED = "qa_triggered"
REVIEWING = "reviewing"
COMPLETED = "completed"
FAILED = "failed"
EXPIRED = "expired"

VALID_TRANSITIONS: dict[str, set[str]] = {
    PENDING: {PLANNING, EXPIRED, FAILED},
    PLANNING: {AWAITING_APPROVAL, EXECUTING, FAILED},
    AWAITING_APPROVAL: {EXECUTING, FAILED},
    EXECUTING: {SECURITY_SCANNING, FAILED},
    SECURITY_SCANNING: {MR_CREATING, FAILED},
    MR_CREATING: {MR_CREATED, FAILED},
    MR_CREATED: {QA_TRIGGERED, FAILED},
    QA_TRIGGERED: {REVIEWING, FAILED},
    REVIEWING: {COMPLETED, FAILED},
    COMPLETED: set(),
    FAILED: {PLANNING},
    EXPIRED: set(),
}

ACTIVE_STATUSES: tuple[str, ...] = (
    EXECUTING,
    SECURITY_SCANNING,
    MR_CREATING,
    MR_CREATED,
    QA_TRIGGERED,
    REVIEWING,
)

IN_PROGRESS_STATUSES: tuple[str, ...] = (
    PLANNING,
    AWAITING_APPROVAL,
    *ACTIVE_STATUSES,
)


def can_transition(from_status: str, to_status: str) -> bool:
    """Return whether a delivery task can move between two lifecycle states."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


__all__ = [
    "ACTIVE_STATUSES",
    "AWAITING_APPROVAL",
    "COMPLETED",
    "EXECUTING",
    "EXPIRED",
    "FAILED",
    "IN_PROGRESS_STATUSES",
    "MR_CREATED",
    "MR_CREATING",
    "PENDING",
    "PLANNING",
    "QA_TRIGGERED",
    "REVIEWING",
    "SECURITY_SCANNING",
    "VALID_TRANSITIONS",
    "can_transition",
]
