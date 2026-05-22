"""Unit tests for the AgentRun aggregate seed (DDD-001)."""

from __future__ import annotations

import pytest

from shared.control_plane.domain.agent_run import (
    AgentRun,
    AgentRunStatusChanged,
    InvalidAgentRunTransitionError,
    VALID_TRANSITIONS,
)
from shared.control_plane.models import AgentRun as AgentRunRecord
from shared.control_plane.models import AgentRunStatus


def _make_record(status: AgentRunStatus = AgentRunStatus.PENDING) -> AgentRunRecord:
    return AgentRunRecord(
        company_id="cmp_test",
        agent_id="dev-agent",
        status=status,
    )


def test_pending_can_transition_to_running() -> None:
    aggregate = AgentRun.from_record(_make_record())
    aggregate.transition_to(AgentRunStatus.RUNNING)
    assert aggregate.status == AgentRunStatus.RUNNING


def test_pending_cannot_transition_to_succeeded_directly() -> None:
    aggregate = AgentRun.from_record(_make_record())
    with pytest.raises(InvalidAgentRunTransitionError):
        aggregate.transition_to(AgentRunStatus.SUCCEEDED)


def test_running_can_transition_to_succeeded() -> None:
    aggregate = AgentRun.from_record(_make_record(AgentRunStatus.RUNNING))
    aggregate.transition_to(AgentRunStatus.SUCCEEDED)
    assert aggregate.status == AgentRunStatus.SUCCEEDED


def test_terminal_states_are_terminal() -> None:
    for terminal in (
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.TIMED_OUT,
    ):
        aggregate = AgentRun.from_record(_make_record(terminal))
        assert aggregate.is_terminal
        with pytest.raises(InvalidAgentRunTransitionError):
            aggregate.transition_to(AgentRunStatus.RUNNING)


def test_transition_raises_typed_domain_event() -> None:
    aggregate = AgentRun.from_record(_make_record())
    aggregate.transition_to(AgentRunStatus.RUNNING)
    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, AgentRunStatusChanged)
    assert event.from_status == AgentRunStatus.PENDING
    assert event.to_status == AgentRunStatus.RUNNING


def test_pull_events_clears_the_buffer() -> None:
    aggregate = AgentRun.from_record(_make_record())
    aggregate.transition_to(AgentRunStatus.RUNNING)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_valid_transitions_table_covers_every_status() -> None:
    for status in AgentRunStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"
