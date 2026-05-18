"""Unit tests for the Decomposition aggregate."""

from __future__ import annotations

import pytest

from agents.pjm_agent.core.domain.decomposition import (
    Decomposition,
    DecompositionStatusChanged,
    InvalidDecompositionTransitionError,
)
from agents.pjm_agent.core.domain.lifecycle.decomposition_lifecycle import (
    APPROVED,
    FAILED,
    PENDING,
    REJECTED,
    WRITE_FAILED,
    WRITING,
)


def test_construct_with_valid_status():
    agg = Decomposition(wp_id=1, status=PENDING)
    assert agg.status == PENDING
    assert agg.wp_id == 1
    assert agg.pending_events == []


def test_construct_with_invalid_status_raises():
    with pytest.raises(ValueError):
        Decomposition(wp_id=1, status="bogus")


def test_legal_transition_pending_to_writing_records_event():
    agg = Decomposition(wp_id=42, status=PENDING)
    event = agg.transition_to(WRITING)

    assert agg.status == WRITING
    assert isinstance(event, DecompositionStatusChanged)
    assert event.wp_id == 42
    assert event.from_status == PENDING
    assert event.to_status == WRITING
    assert agg.pending_events == [event]


def test_legal_transition_writing_to_approved():
    agg = Decomposition(wp_id=1, status=WRITING)
    agg.transition_to(APPROVED)
    assert agg.status == APPROVED


def test_illegal_transition_raises_typed_error():
    agg = Decomposition(wp_id=99, status=APPROVED)
    with pytest.raises(InvalidDecompositionTransitionError) as exc_info:
        agg.transition_to(PENDING)

    assert exc_info.value.wp_id == 99
    assert exc_info.value.from_status == APPROVED
    assert exc_info.value.to_status == PENDING
    # No state change on illegal transition.
    assert agg.status == APPROVED
    assert agg.pending_events == []


def test_unknown_target_status_raises_typed_error():
    agg = Decomposition(wp_id=1, status=PENDING)
    with pytest.raises(InvalidDecompositionTransitionError):
        agg.transition_to("garbage")
    assert agg.status == PENDING


def test_terminal_states_block_further_transitions():
    for terminal in (APPROVED, REJECTED, FAILED):
        agg = Decomposition(wp_id=1, status=terminal)
        assert agg.is_terminal()
        for target in (PENDING, WRITING, APPROVED, REJECTED, FAILED, WRITE_FAILED):
            if target == terminal:
                # Self-transition is also illegal in this policy.
                with pytest.raises(InvalidDecompositionTransitionError):
                    agg.transition_to(target)
            else:
                with pytest.raises(InvalidDecompositionTransitionError):
                    agg.transition_to(target)


def test_pull_events_drains_buffer():
    agg = Decomposition(wp_id=7, status=PENDING)
    agg.transition_to(WRITING)
    agg.transition_to(WRITE_FAILED)
    agg.transition_to(WRITING)
    agg.transition_to(APPROVED)

    events = agg.pull_events()
    assert len(events) == 4
    assert [e.to_status for e in events] == [WRITING, WRITE_FAILED, WRITING, APPROVED]
    # Second drain returns no events.
    assert agg.pull_events() == []


def test_write_failed_can_retry_via_writing():
    agg = Decomposition(wp_id=1, status=WRITE_FAILED)
    agg.transition_to(WRITING)
    agg.transition_to(APPROVED)
    assert agg.status == APPROVED


def test_is_terminal_false_for_active_states():
    for s in (PENDING, WRITING, WRITE_FAILED):
        agg = Decomposition(wp_id=1, status=s)
        assert not agg.is_terminal()


def test_event_is_immutable_value_object():
    event = DecompositionStatusChanged(wp_id=1, from_status=PENDING, to_status=WRITING)
    with pytest.raises((AttributeError, Exception)):
        event.to_status = APPROVED  # type: ignore[misc]
