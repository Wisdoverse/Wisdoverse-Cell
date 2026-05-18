"""Requirement lifecycle policy tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from agents.requirement_manager.core.requirement_lifecycle import (
    CONFIRMED,
    REJECTED,
    mark_confirmed,
    mark_rejected,
    record_updated,
)


@dataclass
class RequirementDouble:
    status: str = "pending"
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    rejection_reason: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    def add_history(self, action: str, detail: str, by: str) -> None:
        self.history.append({"action": action, "detail": detail, "by": by})


def test_mark_confirmed_sets_status_metadata_and_history() -> None:
    requirement = RequirementDouble()
    confirmed_at = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)

    mark_confirmed(requirement, "product-owner", now=confirmed_at)

    assert requirement.status == CONFIRMED
    assert requirement.confirmed_by == "product-owner"
    assert requirement.confirmed_at == confirmed_at
    assert requirement.history == [
        {"action": "confirmed", "detail": "需求已确认", "by": "product-owner"}
    ]


def test_mark_rejected_sets_status_reason_and_history() -> None:
    requirement = RequirementDouble()

    mark_rejected(requirement, "Out of scope", "product-owner")

    assert requirement.status == REJECTED
    assert requirement.rejection_reason == "Out of scope"
    assert requirement.history == [
        {
            "action": "rejected",
            "detail": "需求已拒绝: Out of scope",
            "by": "product-owner",
        }
    ]


def test_record_updated_adds_history_without_status_change() -> None:
    requirement = RequirementDouble()

    record_updated(requirement, ["title", "priority"], "operator")

    assert requirement.status == "pending"
    assert requirement.history == [
        {
            "action": "updated",
            "detail": "Updated fields: ['title', 'priority']",
            "by": "operator",
        }
    ]
