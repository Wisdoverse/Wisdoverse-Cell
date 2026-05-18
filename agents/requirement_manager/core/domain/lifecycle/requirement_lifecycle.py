"""Requirement lifecycle policy.

The requirement domain owns status changes and history entries. Persistence
adapters call these functions instead of embedding lifecycle writes directly.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

PENDING = "pending"
CONFIRMED = "confirmed"
CHANGED = "changed"
REJECTED = "rejected"


class MutableRequirement(Protocol):
    """Fields required by requirement lifecycle transitions."""

    status: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    rejection_reason: str | None

    def add_history(self, action: str, detail: str, by: str) -> None:
        """Append a requirement history entry."""


def mark_confirmed(
    requirement: MutableRequirement,
    confirmed_by: str,
    *,
    now: datetime | None = None,
) -> None:
    """Apply the confirmed lifecycle transition to a requirement."""
    confirmed_at = now or datetime.now(UTC)
    requirement.status = CONFIRMED
    requirement.confirmed_by = confirmed_by
    requirement.confirmed_at = confirmed_at
    requirement.add_history("confirmed", "需求已确认", confirmed_by)


def mark_rejected(
    requirement: MutableRequirement,
    reason: str,
    rejected_by: str,
) -> None:
    """Apply the rejected lifecycle transition to a requirement."""
    requirement.status = REJECTED
    requirement.rejection_reason = reason
    requirement.add_history("rejected", f"需求已拒绝: {reason}", rejected_by)


def record_updated(
    requirement: MutableRequirement,
    changed_fields: list[str],
    changed_by: str,
) -> None:
    """Record a requirement update in the domain history."""
    requirement.add_history(
        "updated",
        f"Updated fields: {changed_fields}",
        changed_by,
    )


__all__ = [
    "CHANGED",
    "CONFIRMED",
    "MutableRequirement",
    "PENDING",
    "REJECTED",
    "mark_confirmed",
    "mark_rejected",
    "record_updated",
]
