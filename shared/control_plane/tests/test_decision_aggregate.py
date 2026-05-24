"""Unit tests for the Decision aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.decision import (
    TERMINAL_STATUSES,
    VALID_TRANSITIONS,
    Decision,
    DecisionStatusChanged,
    InvalidDecisionTransitionError,
    decision_status,
)
from shared.control_plane.models import Decision as DecisionRecord
from shared.control_plane.models import DecisionStatus


def _make_record(status: DecisionStatus = DecisionStatus.PROPOSED) -> DecisionRecord:
    return DecisionRecord(
        company_id="cmp_test",
        title="Choose launch path",
        rationale="Operator decision is required.",
        status=status,
    )


def test_proposed_decision_can_be_accepted() -> None:
    aggregate = Decision.from_record(_make_record())
    aggregate.transition_to(DecisionStatus.ACCEPTED)
    assert aggregate.status == DecisionStatus.ACCEPTED


def test_proposed_decision_can_be_rejected() -> None:
    aggregate = Decision.from_record(_make_record())
    aggregate.transition_to(DecisionStatus.REJECTED)
    assert aggregate.status == DecisionStatus.REJECTED


def test_accepted_decision_can_be_superseded() -> None:
    aggregate = Decision.from_record(_make_record(DecisionStatus.ACCEPTED))
    aggregate.transition_to(DecisionStatus.SUPERSEDED)
    assert aggregate.status == DecisionStatus.SUPERSEDED


def test_accepted_decision_cannot_be_rejected() -> None:
    aggregate = Decision.from_record(_make_record(DecisionStatus.ACCEPTED))
    with pytest.raises(InvalidDecisionTransitionError):
        aggregate.transition_to(DecisionStatus.REJECTED)
    assert aggregate.status == DecisionStatus.ACCEPTED


def test_same_status_transition_is_noop() -> None:
    aggregate = Decision.from_record(_make_record(DecisionStatus.PROPOSED))
    aggregate.transition_to(DecisionStatus.PROPOSED)
    assert aggregate.status == DecisionStatus.PROPOSED
    assert aggregate.pull_events() == []


def test_transition_raises_typed_domain_event() -> None:
    aggregate = Decision.from_record(_make_record())
    aggregate.transition_to(DecisionStatus.ACCEPTED)
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, DecisionStatusChanged)
    assert event.from_status == DecisionStatus.PROPOSED
    assert event.to_status == DecisionStatus.ACCEPTED


def test_pull_events_clears_buffer() -> None:
    aggregate = Decision.from_record(_make_record())
    aggregate.transition_to(DecisionStatus.ACCEPTED)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_status_changed_event_is_frozen_value_object() -> None:
    event = DecisionStatusChanged(
        decision_id="dec_1",
        company_id="cmp_test",
        from_status=DecisionStatus.PROPOSED,
        to_status=DecisionStatus.ACCEPTED,
    )
    with pytest.raises(FrozenInstanceError):
        event.to_status = DecisionStatus.REJECTED  # type: ignore[misc]


def test_valid_transitions_table_covers_every_status() -> None:
    for status in DecisionStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"


def test_terminal_statuses_match_empty_transition_rows() -> None:
    derived = {status for status, allowed in VALID_TRANSITIONS.items() if not allowed}
    assert TERMINAL_STATUSES == derived


def test_status_parser_accepts_strings_and_enums() -> None:
    assert decision_status(DecisionStatus.ACCEPTED) == DecisionStatus.ACCEPTED
    assert decision_status("rejected") == DecisionStatus.REJECTED
    assert decision_status(None) is None
