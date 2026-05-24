"""Dev task lifecycle policy.

This module owns the domain-level state machine for delivery tasks. Persistence
adapters call these functions instead of carrying transition rules themselves.
"""

from __future__ import annotations

from typing import NewType

TaskStatus = NewType("TaskStatus", str)

PENDING = TaskStatus("pending")
PLANNING = TaskStatus("planning")
AWAITING_APPROVAL = TaskStatus("awaiting_approval")
EXECUTING = TaskStatus("executing")
SECURITY_SCANNING = TaskStatus("security_scanning")
MR_CREATING = TaskStatus("mr_creating")
MR_CREATED = TaskStatus("mr_created")
QA_TRIGGERED = TaskStatus("qa_triggered")
REVIEWING = TaskStatus("reviewing")
COMPLETED = TaskStatus("completed")
FAILED = TaskStatus("failed")
EXPIRED = TaskStatus("expired")

VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
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

ACTIVE_STATUSES: tuple[TaskStatus, ...] = (
    EXECUTING,
    SECURITY_SCANNING,
    MR_CREATING,
    MR_CREATED,
    QA_TRIGGERED,
    REVIEWING,
)

IN_PROGRESS_STATUSES: tuple[TaskStatus, ...] = (
    PLANNING,
    AWAITING_APPROVAL,
    *ACTIVE_STATUSES,
)


def can_transition(from_status: TaskStatus | str, to_status: TaskStatus | str) -> bool:
    """Return whether a delivery task can move between two lifecycle states."""
    return TaskStatus(str(to_status)) in VALID_TRANSITIONS.get(
        TaskStatus(str(from_status)),
        set(),
    )


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
    "TaskStatus",
    "VALID_TRANSITIONS",
    "can_transition",
]
