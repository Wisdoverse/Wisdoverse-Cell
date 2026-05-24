"""Unit tests for the Goal aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.goal import (
    TERMINAL_STATUSES,
    VALID_TRANSITIONS,
    Goal,
    GoalStatusChanged,
    InvalidGoalTransitionError,
    goal_current_value_for_transition,
    goal_status,
)
from shared.control_plane.models import Goal as GoalRecord
from shared.control_plane.models import GoalStatus


def _make_record(
    status: GoalStatus = GoalStatus.DRAFT,
    *,
    target_value: float | None = None,
) -> GoalRecord:
    return GoalRecord(
        company_id="cmp_test",
        title="Ship company objective",
        status=status,
        target_value=target_value,
    )


def test_draft_goal_can_activate() -> None:
    aggregate = Goal.from_record(_make_record())
    aggregate.transition_to(GoalStatus.ACTIVE)
    assert aggregate.status == GoalStatus.ACTIVE


def test_completed_goal_can_reopen() -> None:
    aggregate = Goal.from_record(_make_record(GoalStatus.COMPLETED))
    aggregate.transition_to(GoalStatus.ACTIVE)
    assert aggregate.status == GoalStatus.ACTIVE


def test_cancelled_goal_cannot_restart() -> None:
    aggregate = Goal.from_record(_make_record(GoalStatus.CANCELLED))
    with pytest.raises(InvalidGoalTransitionError):
        aggregate.transition_to(GoalStatus.ACTIVE)
    assert aggregate.status == GoalStatus.CANCELLED


def test_same_status_transition_is_noop() -> None:
    aggregate = Goal.from_record(_make_record(GoalStatus.ACTIVE))
    aggregate.transition_to(GoalStatus.ACTIVE)
    assert aggregate.status == GoalStatus.ACTIVE
    assert aggregate.pull_events() == []


def test_transition_raises_typed_domain_event() -> None:
    aggregate = Goal.from_record(_make_record())
    aggregate.transition_to(GoalStatus.ACTIVE)
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, GoalStatusChanged)
    assert event.from_status == GoalStatus.DRAFT
    assert event.to_status == GoalStatus.ACTIVE


def test_pull_events_clears_buffer() -> None:
    aggregate = Goal.from_record(_make_record())
    aggregate.transition_to(GoalStatus.ACTIVE)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_status_changed_event_is_frozen_value_object() -> None:
    event = GoalStatusChanged(
        goal_id="goal_1",
        company_id="cmp_test",
        from_status=GoalStatus.DRAFT,
        to_status=GoalStatus.ACTIVE,
    )
    with pytest.raises(FrozenInstanceError):
        event.to_status = GoalStatus.COMPLETED  # type: ignore[misc]


def test_valid_transitions_table_covers_every_status() -> None:
    for status in GoalStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"


def test_cancelled_is_terminal_status() -> None:
    assert TERMINAL_STATUSES == frozenset({GoalStatus.CANCELLED})
    assert Goal.from_record(_make_record(GoalStatus.CANCELLED)).is_terminal
    assert not Goal.from_record(_make_record(GoalStatus.COMPLETED)).is_terminal


def test_completed_goal_without_explicit_progress_uses_target_value() -> None:
    aggregate = Goal.from_record(_make_record(GoalStatus.ACTIVE, target_value=100))
    aggregate.transition_to(GoalStatus.COMPLETED)
    assert aggregate.current_value_for_update(None) == 100


def test_explicit_progress_takes_precedence_over_target_value() -> None:
    assert (
        goal_current_value_for_transition(
            target_status=GoalStatus.COMPLETED,
            explicit_current_value=95,
            target_value=100,
        )
        == 95
    )


def test_status_parser_accepts_strings_and_enums() -> None:
    assert goal_status(GoalStatus.PAUSED) == GoalStatus.PAUSED
    assert goal_status("completed") == GoalStatus.COMPLETED
    assert goal_status(None) is None
