"""Unit tests for the decomposition lifecycle domain module."""

from agents.pjm_agent.core.domain.lifecycle.decomposition_lifecycle import (
    APPROVED,
    DECOMPOSITION_STATUSES,
    FAILED,
    PENDING,
    REJECTED,
    TERMINAL_STATUSES,
    VALID_TRANSITIONS,
    WRITE_FAILED,
    WRITING,
    can_transition,
    is_terminal,
)


def test_decomposition_statuses_enumerated():
    """Every status referenced in code appears in the enumeration."""
    assert set(DECOMPOSITION_STATUSES) == {
        PENDING,
        WRITING,
        APPROVED,
        WRITE_FAILED,
        FAILED,
        REJECTED,
    }


def test_terminal_states_have_no_outgoing_transitions():
    """Terminal states must not have outgoing transitions."""
    for status in TERMINAL_STATUSES:
        assert VALID_TRANSITIONS[status] == set()
        assert is_terminal(status)


def test_pending_can_advance_to_writing_or_terminal():
    """A pending decomposition can advance toward writing or any terminal verdict."""
    assert can_transition(PENDING, WRITING)
    assert can_transition(PENDING, APPROVED)
    assert can_transition(PENDING, REJECTED)
    assert can_transition(PENDING, FAILED)
    assert can_transition(PENDING, WRITE_FAILED)


def test_writing_can_advance_only_within_lifecycle():
    """A writing decomposition may finish, fail, or fall back to write_failed."""
    assert can_transition(WRITING, APPROVED)
    assert can_transition(WRITING, WRITE_FAILED)
    assert can_transition(WRITING, FAILED)
    assert not can_transition(WRITING, PENDING)
    assert not can_transition(WRITING, REJECTED)


def test_write_failed_can_retry_or_terminate():
    """write_failed may retry the write or terminate via failed/rejected."""
    assert can_transition(WRITE_FAILED, WRITING)
    assert can_transition(WRITE_FAILED, FAILED)
    assert can_transition(WRITE_FAILED, REJECTED)
    assert not can_transition(WRITE_FAILED, APPROVED)


def test_terminal_states_cannot_re_enter():
    """Approved/rejected/failed records do not transition again."""
    for terminal in (APPROVED, REJECTED, FAILED):
        for any_other in DECOMPOSITION_STATUSES:
            assert not can_transition(terminal, any_other)


def test_unknown_status_yields_no_transitions():
    """An unrecognized starting state has no valid transitions."""
    assert not can_transition("unknown", PENDING)
    assert not can_transition("garbage", APPROVED)


def test_is_terminal_only_for_terminal_set():
    """is_terminal returns True only for APPROVED, REJECTED, FAILED."""
    assert is_terminal(APPROVED)
    assert is_terminal(REJECTED)
    assert is_terminal(FAILED)
    assert not is_terminal(PENDING)
    assert not is_terminal(WRITING)
    assert not is_terminal(WRITE_FAILED)
