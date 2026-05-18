"""Unit tests for the Requirement aggregate + FSM."""

from __future__ import annotations

import pytest

from agents.requirement_manager.core.domain.lifecycle.requirement_lifecycle import (
    CHANGED,
    CONFIRMED,
    PENDING,
    REJECTED,
)
from agents.requirement_manager.core.domain.lifecycle.requirement_states import (
    can_transition,
    is_terminal,
)
from agents.requirement_manager.core.domain.requirement import (
    InvalidRequirementTransitionError,
    Requirement,
    RequirementStatusChanged,
)

# --- FSM rules ---


def test_fsm_pending_can_advance():
    assert can_transition(PENDING, CONFIRMED)
    assert can_transition(PENDING, REJECTED)
    assert can_transition(PENDING, CHANGED)


def test_fsm_confirmed_can_change_or_reject():
    assert can_transition(CONFIRMED, CHANGED)
    assert can_transition(CONFIRMED, REJECTED)
    assert not can_transition(CONFIRMED, PENDING)


def test_fsm_changed_can_re_confirm_or_reject():
    assert can_transition(CHANGED, CONFIRMED)
    assert can_transition(CHANGED, REJECTED)
    assert not can_transition(CHANGED, PENDING)


def test_fsm_rejected_is_terminal():
    assert is_terminal(REJECTED)
    for target in (PENDING, CONFIRMED, CHANGED):
        assert not can_transition(REJECTED, target)


# --- Aggregate ---


def test_construct_with_valid_status():
    req = Requirement(requirement_id="r-1", status=PENDING)
    assert req.status == PENDING
    assert req.pending_events == []


def test_construct_with_invalid_status_raises():
    with pytest.raises(ValueError):
        Requirement(requirement_id="r-1", status="bogus")


def test_legal_transition_records_event():
    req = Requirement(requirement_id="r-42", status=PENDING)
    event = req.transition_to(CONFIRMED, actor_id="user-7")

    assert req.status == CONFIRMED
    assert isinstance(event, RequirementStatusChanged)
    assert event.requirement_id == "r-42"
    assert event.from_status == PENDING
    assert event.to_status == CONFIRMED
    assert event.actor_id == "user-7"
    assert req.pending_events == [event]


def test_illegal_transition_raises_typed_error():
    req = Requirement(requirement_id="r-99", status=REJECTED)
    with pytest.raises(InvalidRequirementTransitionError) as exc_info:
        req.transition_to(CONFIRMED)

    assert exc_info.value.requirement_id == "r-99"
    assert exc_info.value.from_status == REJECTED
    assert exc_info.value.to_status == CONFIRMED
    # State unchanged.
    assert req.status == REJECTED
    assert req.pending_events == []


def test_unknown_target_status_raises():
    req = Requirement(requirement_id="r-1", status=PENDING)
    with pytest.raises(InvalidRequirementTransitionError):
        req.transition_to("garbage")


def test_confirm_then_edit_then_reconfirm():
    req = Requirement(requirement_id="r-1", status=PENDING)
    req.transition_to(CONFIRMED)
    req.transition_to(CHANGED)
    req.transition_to(CONFIRMED)
    assert req.status == CONFIRMED
    assert len(req.pending_events) == 3


def test_pull_events_drains_buffer():
    req = Requirement(requirement_id="r-1", status=PENDING)
    req.transition_to(CONFIRMED)
    req.transition_to(CHANGED)
    events = req.pull_events()
    assert len(events) == 2
    assert req.pull_events() == []


def test_actor_id_optional_on_event():
    req = Requirement(requirement_id="r-1", status=PENDING)
    event = req.transition_to(CONFIRMED)
    assert event.actor_id is None


def test_event_is_immutable_value_object():
    event = RequirementStatusChanged(
        requirement_id="r-1", from_status=PENDING, to_status=CONFIRMED
    )
    with pytest.raises((AttributeError, Exception)):
        event.to_status = REJECTED  # type: ignore[misc]
