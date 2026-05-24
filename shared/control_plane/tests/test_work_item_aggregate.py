"""Unit tests for the WorkItem aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.work_item import (
    VALID_TRANSITIONS,
    WORK_ITEM_CLOSE_STATUSES,
    InvalidWorkItemTransitionError,
    WorkItem,
    WorkItemStatusChanged,
    is_work_item_close_status,
    work_item_status,
    work_item_status_from_agent_run_status,
)
from shared.control_plane.models import (
    AgentRunStatus,
    WorkItemStatus,
)
from shared.control_plane.models import (
    WorkItem as WorkItemRecord,
)


def _make_record(status: WorkItemStatus = WorkItemStatus.QUEUED) -> WorkItemRecord:
    return WorkItemRecord(
        company_id="cmp_test",
        title="Deliver agent task",
        status=status,
    )


def test_queued_work_item_can_start_running() -> None:
    aggregate = WorkItem.from_record(_make_record())
    aggregate.transition_to(WorkItemStatus.RUNNING)
    assert aggregate.status == WorkItemStatus.RUNNING


def test_completed_work_item_can_reopen_for_retry() -> None:
    aggregate = WorkItem.from_record(_make_record(WorkItemStatus.COMPLETED))
    aggregate.transition_to(WorkItemStatus.RUNNING)
    assert aggregate.status == WorkItemStatus.RUNNING


def test_cancelled_work_item_cannot_restart() -> None:
    aggregate = WorkItem.from_record(_make_record(WorkItemStatus.CANCELLED))
    with pytest.raises(InvalidWorkItemTransitionError):
        aggregate.transition_to(WorkItemStatus.RUNNING)
    assert aggregate.status == WorkItemStatus.CANCELLED


def test_failed_work_item_can_retry_running() -> None:
    aggregate = WorkItem.from_record(_make_record(WorkItemStatus.FAILED))
    aggregate.transition_to(WorkItemStatus.RUNNING)
    assert aggregate.status == WorkItemStatus.RUNNING


def test_same_status_transition_is_noop() -> None:
    aggregate = WorkItem.from_record(_make_record(WorkItemStatus.READY))
    aggregate.transition_to(WorkItemStatus.READY)
    assert aggregate.status == WorkItemStatus.READY
    assert aggregate.pull_events() == []


def test_transition_raises_typed_domain_event() -> None:
    aggregate = WorkItem.from_record(_make_record())
    aggregate.transition_to(WorkItemStatus.RUNNING)
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, WorkItemStatusChanged)
    assert event.from_status == WorkItemStatus.QUEUED
    assert event.to_status == WorkItemStatus.RUNNING


def test_pull_events_clears_buffer() -> None:
    aggregate = WorkItem.from_record(_make_record())
    aggregate.transition_to(WorkItemStatus.RUNNING)
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_status_changed_event_is_frozen_value_object() -> None:
    event = WorkItemStatusChanged(
        work_item_id="work_1",
        company_id="cmp_test",
        from_status=WorkItemStatus.QUEUED,
        to_status=WorkItemStatus.RUNNING,
    )
    with pytest.raises(FrozenInstanceError):
        event.to_status = WorkItemStatus.COMPLETED  # type: ignore[misc]


def test_valid_transitions_table_covers_every_status() -> None:
    for status in WorkItemStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"


def test_close_status_policy_lives_in_domain() -> None:
    assert WORK_ITEM_CLOSE_STATUSES == frozenset(
        {
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED,
        }
    )
    assert is_work_item_close_status(WorkItemStatus.COMPLETED)
    assert is_work_item_close_status("failed")
    assert not is_work_item_close_status(WorkItemStatus.RUNNING)


def test_agent_run_status_maps_to_work_item_status() -> None:
    assert (
        work_item_status_from_agent_run_status(AgentRunStatus.SUCCEEDED) == WorkItemStatus.COMPLETED
    )
    assert work_item_status_from_agent_run_status("failed") == WorkItemStatus.FAILED
    assert (
        work_item_status_from_agent_run_status(AgentRunStatus.CANCELLED) == WorkItemStatus.CANCELLED
    )
    assert work_item_status_from_agent_run_status(None) == WorkItemStatus.RUNNING
    assert work_item_status_from_agent_run_status(AgentRunStatus.RUNNING) == WorkItemStatus.RUNNING


def test_status_parser_accepts_strings_and_enums() -> None:
    assert work_item_status(WorkItemStatus.BLOCKED) == WorkItemStatus.BLOCKED
    assert work_item_status("awaiting_approval") == WorkItemStatus.AWAITING_APPROVAL
    assert work_item_status(None) is None
