"""Unit tests for the ApprovalRequest aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.approval_request import (
    TERMINAL_STATUSES,
    VALID_TRANSITIONS,
    ApprovalRequest,
    ApprovalStatusChanged,
    InvalidApprovalTransitionError,
    approval_status,
    approval_status_is_approved,
)
from shared.control_plane.models import ApprovalCategory, ApprovalStatus
from shared.control_plane.models import ApprovalRequest as ApprovalRequestRecord


def _make_record(
    status: ApprovalStatus = ApprovalStatus.PENDING,
) -> ApprovalRequestRecord:
    return ApprovalRequestRecord(
        company_id="cmp_test",
        category=ApprovalCategory.TECHNICAL,
        status=status,
        requested_by="agent:dev-agent",
        source_agent_id="dev-agent",
        proposed_action="Run sensitive workflow",
        reason="Sensitive workflow needs human approval.",
        risk="Incorrect approval could affect production.",
        rollback_note="Cancel the workflow before execution.",
        affected_resources=["runtime"],
    )


def test_pending_approval_can_be_approved() -> None:
    aggregate = ApprovalRequest.from_record(_make_record())
    aggregate.transition_to(ApprovalStatus.APPROVED)
    assert aggregate.status == ApprovalStatus.APPROVED
    assert aggregate.is_approved


def test_pending_approval_can_be_rejected() -> None:
    aggregate = ApprovalRequest.from_record(_make_record())
    aggregate.transition_to(ApprovalStatus.REJECTED)
    assert aggregate.status == ApprovalStatus.REJECTED
    assert not aggregate.is_approved


def test_approved_approval_cannot_be_rejected() -> None:
    aggregate = ApprovalRequest.from_record(_make_record(ApprovalStatus.APPROVED))
    with pytest.raises(InvalidApprovalTransitionError):
        aggregate.transition_to(ApprovalStatus.REJECTED)
    assert aggregate.status == ApprovalStatus.APPROVED


def test_rejected_approval_cannot_be_approved() -> None:
    aggregate = ApprovalRequest.from_record(_make_record(ApprovalStatus.REJECTED))
    with pytest.raises(InvalidApprovalTransitionError):
        aggregate.transition_to(ApprovalStatus.APPROVED)
    assert aggregate.status == ApprovalStatus.REJECTED


def test_same_status_transition_is_noop() -> None:
    aggregate = ApprovalRequest.from_record(_make_record(ApprovalStatus.APPROVED))
    aggregate.transition_to(ApprovalStatus.APPROVED)
    assert aggregate.status == ApprovalStatus.APPROVED
    assert aggregate.pull_events() == []


def test_transition_raises_typed_domain_event() -> None:
    aggregate = ApprovalRequest.from_record(_make_record())
    aggregate.transition_to(ApprovalStatus.APPROVED)
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ApprovalStatusChanged)
    assert event.from_status == ApprovalStatus.PENDING
    assert event.to_status == ApprovalStatus.APPROVED


def test_pull_events_clears_buffer() -> None:
    aggregate = ApprovalRequest.from_record(_make_record())
    aggregate.transition_to(ApprovalStatus.APPROVED)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_status_changed_event_is_frozen_value_object() -> None:
    event = ApprovalStatusChanged(
        approval_id="appr_1",
        company_id="cmp_test",
        from_status=ApprovalStatus.PENDING,
        to_status=ApprovalStatus.APPROVED,
    )
    with pytest.raises(FrozenInstanceError):
        event.to_status = ApprovalStatus.REJECTED  # type: ignore[misc]


def test_valid_transitions_table_covers_every_status() -> None:
    for status in ApprovalStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"


def test_resolved_statuses_are_terminal() -> None:
    assert TERMINAL_STATUSES == frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    )
    assert ApprovalRequest.from_record(_make_record(ApprovalStatus.APPROVED)).is_terminal
    assert not ApprovalRequest.from_record(_make_record()).is_terminal


def test_approval_status_policy_accepts_strings_and_enums() -> None:
    assert approval_status(ApprovalStatus.PENDING) == ApprovalStatus.PENDING
    assert approval_status("approved") == ApprovalStatus.APPROVED
    assert approval_status(None) is None
    assert approval_status_is_approved(ApprovalStatus.APPROVED)
    assert approval_status_is_approved("approved")
    assert not approval_status_is_approved(ApprovalStatus.REJECTED)
