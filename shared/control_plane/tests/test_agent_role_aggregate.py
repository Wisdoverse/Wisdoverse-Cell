"""Unit tests for the AgentRole aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.agent_role import (
    RUNNABLE_STATUSES,
    TERMINAL_STATUSES,
    VALID_TRANSITIONS,
    AgentRole,
    AgentRoleStatus,
    AgentRoleStatusChanged,
    InvalidAgentRoleStatusError,
    InvalidAgentRoleTransitionError,
    agent_role_status,
)
from shared.control_plane.models import AgentRole as AgentRoleRecord


def _make_record(status: str = AgentRoleStatus.ACTIVE.value) -> AgentRoleRecord:
    return AgentRoleRecord(
        company_id="cmp_test",
        agent_id="ops-runner",
        display_name="Ops Runner",
        status=status,
    )


def test_active_agent_role_can_pause() -> None:
    aggregate = AgentRole.from_record(_make_record())
    aggregate.transition_to(AgentRoleStatus.PAUSED)
    assert aggregate.status == AgentRoleStatus.PAUSED


def test_retired_agent_role_is_terminal() -> None:
    aggregate = AgentRole.from_record(_make_record(AgentRoleStatus.RETIRED.value))

    with pytest.raises(InvalidAgentRoleTransitionError):
        aggregate.transition_to(AgentRoleStatus.ACTIVE)

    assert aggregate.is_terminal
    assert aggregate.status == AgentRoleStatus.RETIRED


def test_same_status_transition_is_noop() -> None:
    aggregate = AgentRole.from_record(_make_record(AgentRoleStatus.PAUSED.value))
    aggregate.transition_to("paused")

    assert aggregate.status == AgentRoleStatus.PAUSED
    assert aggregate.pull_events() == []


def test_only_active_agent_roles_are_runnable() -> None:
    assert RUNNABLE_STATUSES == frozenset({AgentRoleStatus.ACTIVE})
    assert AgentRole.from_record(_make_record()).is_runnable
    assert not AgentRole.from_record(_make_record(AgentRoleStatus.PAUSED.value)).is_runnable
    assert not AgentRole.from_record(_make_record(AgentRoleStatus.DISABLED.value)).is_runnable


def test_transition_raises_typed_domain_event() -> None:
    aggregate = AgentRole.from_record(_make_record())
    aggregate.transition_to("disabled")
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, AgentRoleStatusChanged)
    assert event.from_status == AgentRoleStatus.ACTIVE
    assert event.to_status == AgentRoleStatus.DISABLED
    assert event.agent_id == "ops-runner"


def test_pull_events_clears_buffer() -> None:
    aggregate = AgentRole.from_record(_make_record())
    aggregate.transition_to(AgentRoleStatus.PAUSED)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_status_changed_event_is_frozen_value_object() -> None:
    event = AgentRoleStatusChanged(
        role_id="role_1",
        agent_id="ops-runner",
        company_id="cmp_test",
        from_status=AgentRoleStatus.ACTIVE,
        to_status=AgentRoleStatus.PAUSED,
    )

    with pytest.raises(FrozenInstanceError):
        event.to_status = AgentRoleStatus.ACTIVE  # type: ignore[misc]


def test_valid_transitions_table_covers_every_status() -> None:
    for status in AgentRoleStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"


def test_terminal_statuses_are_retired_and_terminated() -> None:
    assert TERMINAL_STATUSES == frozenset(
        {AgentRoleStatus.RETIRED, AgentRoleStatus.TERMINATED}
    )


def test_status_parser_accepts_known_strings_and_rejects_unknown_values() -> None:
    assert agent_role_status(" PAUSED ") == AgentRoleStatus.PAUSED
    assert agent_role_status(AgentRoleStatus.DISABLED) == AgentRoleStatus.DISABLED
    assert agent_role_status(None) is None

    with pytest.raises(InvalidAgentRoleStatusError):
        agent_role_status("custom")
