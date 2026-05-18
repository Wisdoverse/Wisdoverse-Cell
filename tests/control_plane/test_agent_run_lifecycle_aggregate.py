"""Unit tests for the control-plane AgentRunLifecycle aggregate."""

from __future__ import annotations

import pytest

from shared.control_plane.domain.agent_run_lifecycle import (
    AgentRunLifecycle,
    AgentRunStatusChanged,
    InvalidAgentRunTransitionError,
    can_transition,
    is_terminal,
)
from shared.control_plane.models import AgentRunStatus


def test_fsm_pending_advances_to_running_or_cancelled():
    assert can_transition(AgentRunStatus.PENDING, AgentRunStatus.RUNNING)
    assert can_transition(AgentRunStatus.PENDING, AgentRunStatus.CANCELLED)


def test_fsm_running_can_reach_all_terminals_except_pending():
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.SUCCEEDED)
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.FAILED)
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED)
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.TIMED_OUT)
    assert not can_transition(AgentRunStatus.RUNNING, AgentRunStatus.PENDING)


def test_terminal_statuses_block_all_outgoing():
    for terminal in (
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.TIMED_OUT,
    ):
        assert is_terminal(terminal)
        for target in AgentRunStatus:
            assert not can_transition(terminal, target)


def test_construct_pending_aggregate():
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.PENDING)
    assert agg.run_id == "r-1"
    assert agg.status == AgentRunStatus.PENDING
    assert agg.pending_events == []
    assert not agg.is_terminal()


def test_legal_transition_records_event():
    agg = AgentRunLifecycle(run_id="r-42", status=AgentRunStatus.PENDING)
    event = agg.transition_to(AgentRunStatus.RUNNING)

    assert agg.status == AgentRunStatus.RUNNING
    assert isinstance(event, AgentRunStatusChanged)
    assert event.run_id == "r-42"
    assert event.from_status == AgentRunStatus.PENDING
    assert event.to_status == AgentRunStatus.RUNNING
    assert agg.pending_events == [event]


def test_full_happy_path():
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.PENDING)
    agg.transition_to(AgentRunStatus.RUNNING)
    agg.transition_to(AgentRunStatus.SUCCEEDED)
    assert agg.status == AgentRunStatus.SUCCEEDED
    assert agg.is_terminal()
    assert len(agg.pending_events) == 2


def test_illegal_transition_raises_typed_error():
    agg = AgentRunLifecycle(run_id="r-99", status=AgentRunStatus.SUCCEEDED)
    with pytest.raises(InvalidAgentRunTransitionError) as exc_info:
        agg.transition_to(AgentRunStatus.RUNNING)

    assert exc_info.value.run_id == "r-99"
    assert exc_info.value.from_status == AgentRunStatus.SUCCEEDED
    assert exc_info.value.to_status == AgentRunStatus.RUNNING
    assert agg.status == AgentRunStatus.SUCCEEDED
    assert agg.pending_events == []


def test_running_to_failed():
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.RUNNING)
    agg.transition_to(AgentRunStatus.FAILED)
    assert agg.status == AgentRunStatus.FAILED
    assert agg.is_terminal()


def test_running_to_timed_out():
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.RUNNING)
    agg.transition_to(AgentRunStatus.TIMED_OUT)
    assert agg.status == AgentRunStatus.TIMED_OUT


def test_pending_cancel_skips_running():
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.PENDING)
    agg.transition_to(AgentRunStatus.CANCELLED)
    assert agg.status == AgentRunStatus.CANCELLED


def test_pending_cannot_jump_to_succeeded():
    """Skipping running -> succeeded would hide what actually happened."""
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.PENDING)
    with pytest.raises(InvalidAgentRunTransitionError):
        agg.transition_to(AgentRunStatus.SUCCEEDED)


def test_pull_events_drains_buffer():
    agg = AgentRunLifecycle(run_id="r-1", status=AgentRunStatus.PENDING)
    agg.transition_to(AgentRunStatus.RUNNING)
    agg.transition_to(AgentRunStatus.SUCCEEDED)
    events = agg.pull_events()
    assert len(events) == 2
    assert agg.pull_events() == []


def test_event_is_immutable_value_object():
    event = AgentRunStatusChanged(
        run_id="r-1",
        from_status=AgentRunStatus.PENDING,
        to_status=AgentRunStatus.RUNNING,
    )
    with pytest.raises((AttributeError, Exception)):
        event.to_status = AgentRunStatus.SUCCEEDED  # type: ignore[misc]
