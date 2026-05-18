"""Unit tests for the dev Task aggregate."""

from __future__ import annotations

import pytest

from agents.dev_agent.core.domain.lifecycle.task_lifecycle import (
    ACTIVE_STATUSES,
    IN_PROGRESS_STATUSES,
    VALID_TRANSITIONS,
)
from agents.dev_agent.core.domain.task import (
    InvalidTaskTransitionError,
    Task,
    TaskStatusChanged,
)


def test_construct_with_valid_status():
    task = Task(task_id="t-1", status="pending")
    assert task.status == "pending"
    assert task.task_id == "t-1"
    assert task.pending_events == []


def test_construct_with_invalid_status_raises():
    with pytest.raises(ValueError):
        Task(task_id="t-1", status="bogus")


def test_legal_transition_pending_to_planning_records_event():
    task = Task(task_id="t-42", status="pending")
    event = task.transition_to("planning")

    assert task.status == "planning"
    assert isinstance(event, TaskStatusChanged)
    assert event.task_id == "t-42"
    assert event.from_status == "pending"
    assert event.to_status == "planning"
    assert task.pending_events == [event]


def test_full_happy_path():
    task = Task(task_id="t-1", status="pending")
    transitions = [
        "planning",
        "awaiting_approval",
        "executing",
        "security_scanning",
        "mr_creating",
        "mr_created",
        "qa_triggered",
        "reviewing",
        "completed",
    ]
    for s in transitions:
        task.transition_to(s)
    assert task.status == "completed"
    assert len(task.pending_events) == len(transitions)


def test_illegal_transition_raises_typed_error():
    task = Task(task_id="t-99", status="completed")
    with pytest.raises(InvalidTaskTransitionError) as exc_info:
        task.transition_to("planning")

    assert exc_info.value.task_id == "t-99"
    assert exc_info.value.from_status == "completed"
    assert exc_info.value.to_status == "planning"
    assert task.status == "completed"
    assert task.pending_events == []


def test_unknown_target_status_raises():
    task = Task(task_id="t-1", status="pending")
    with pytest.raises(InvalidTaskTransitionError):
        task.transition_to("garbage")


def test_failed_can_recover_to_planning():
    task = Task(task_id="t-1", status="failed")
    task.transition_to("planning")
    assert task.status == "planning"


def test_terminal_states_block_transitions():
    for terminal in ("completed", "expired"):
        task = Task(task_id="t-1", status=terminal)
        assert task.is_terminal()
        for any_other in VALID_TRANSITIONS:
            with pytest.raises(InvalidTaskTransitionError):
                task.transition_to(any_other)


def test_is_active_classification():
    for s in ACTIVE_STATUSES:
        task = Task(task_id="t-1", status=s)
        assert task.is_active()
    for s in ("pending", "completed", "failed", "expired"):
        task = Task(task_id="t-1", status=s)
        assert not task.is_active()


def test_is_in_progress_classification():
    for s in IN_PROGRESS_STATUSES:
        task = Task(task_id="t-1", status=s)
        assert task.is_in_progress()
    for s in ("pending", "completed", "failed", "expired"):
        task = Task(task_id="t-1", status=s)
        assert not task.is_in_progress()


def test_pull_events_drains_buffer():
    task = Task(task_id="t-1", status="pending")
    task.transition_to("planning")
    task.transition_to("awaiting_approval")
    events = task.pull_events()
    assert len(events) == 2
    assert task.pull_events() == []


def test_event_is_immutable():
    event = TaskStatusChanged(task_id="t-1", from_status="pending", to_status="planning")
    with pytest.raises((AttributeError, Exception)):
        event.to_status = "completed"  # type: ignore[misc]
