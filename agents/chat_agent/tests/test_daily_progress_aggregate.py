"""Unit tests for the chat-agent DailyProgressEntry aggregate."""

from __future__ import annotations

import pytest

from agents.chat_agent.core.domain.daily_progress import (
    VALID_TRANSITIONS,
    DailyProgressEntry,
    DailyProgressStatus,
    DailyProgressStatusChanged,
    InvalidDailyProgressTransitionError,
    coerce_daily_progress_status,
    daily_progress_context_label,
    is_completed_daily_progress_status,
    is_reported_daily_progress_status,
)


def _entry(status: DailyProgressStatus | str = DailyProgressStatus.PENDING):
    return DailyProgressEntry(
        progress_id=7,
        user_id="ou_user_1",
        task_record_id="rec_task_1",
        task_title="Ship DDD refactor",
        status=status,
    )


def test_construct_normalizes_string_status() -> None:
    entry = _entry("pending")
    assert entry.status == DailyProgressStatus.PENDING
    assert entry.is_open
    assert not entry.has_status_update


def test_construct_requires_known_status() -> None:
    with pytest.raises(ValueError):
        _entry("unknown")


def test_construct_requires_user_id() -> None:
    with pytest.raises(ValueError):
        DailyProgressEntry(
            progress_id=1,
            user_id="",
            task_record_id="rec_task_1",
            task_title="Ship",
            status=DailyProgressStatus.PENDING,
        )


def test_pending_can_be_completed_and_records_event() -> None:
    entry = _entry()
    event = entry.record_update(
        DailyProgressStatus.COMPLETED,
        raw_reply="done",
        note="merged",
    )

    assert entry.status == DailyProgressStatus.COMPLETED
    assert not entry.is_open
    assert entry.has_status_update
    assert entry.raw_reply == "done"
    assert entry.note == "merged"
    assert isinstance(event, DailyProgressStatusChanged)
    assert event.progress_id == 7
    assert event.user_id == "ou_user_1"
    assert event.task_record_id == "rec_task_1"
    assert event.from_status == DailyProgressStatus.PENDING
    assert event.to_status == DailyProgressStatus.COMPLETED
    assert entry.pending_events == [event]


def test_same_status_update_records_note_without_event() -> None:
    entry = _entry(DailyProgressStatus.BLOCKED)

    event = entry.record_update(DailyProgressStatus.BLOCKED, note="waiting on API")

    assert event is None
    assert entry.note == "waiting on API"
    assert entry.pending_events == []


def test_blocked_can_resume_to_in_progress() -> None:
    entry = _entry(DailyProgressStatus.BLOCKED)
    entry.record_update(DailyProgressStatus.IN_PROGRESS)
    assert entry.status == DailyProgressStatus.IN_PROGRESS


def test_completed_can_be_reopened_for_same_day_correction() -> None:
    entry = _entry(DailyProgressStatus.COMPLETED)
    entry.record_update(DailyProgressStatus.BLOCKED)
    assert entry.status == DailyProgressStatus.BLOCKED
    assert entry.is_open


def test_in_progress_cannot_revert_to_pending() -> None:
    entry = _entry(DailyProgressStatus.IN_PROGRESS)
    with pytest.raises(InvalidDailyProgressTransitionError) as exc_info:
        entry.record_update(DailyProgressStatus.PENDING)

    assert exc_info.value.progress_id == 7
    assert exc_info.value.from_status == DailyProgressStatus.IN_PROGRESS
    assert exc_info.value.to_status == DailyProgressStatus.PENDING
    assert entry.status == DailyProgressStatus.IN_PROGRESS
    assert entry.pending_events == []


def test_pull_events_drains_buffer() -> None:
    entry = _entry()
    entry.record_update(DailyProgressStatus.IN_PROGRESS)
    entry.record_update(DailyProgressStatus.COMPLETED)

    events = entry.pull_events()

    assert len(events) == 2
    assert entry.pull_events() == []


def test_status_event_is_immutable() -> None:
    event = DailyProgressStatusChanged(
        progress_id=7,
        user_id="ou_user_1",
        task_record_id="rec_task_1",
        from_status=DailyProgressStatus.PENDING,
        to_status=DailyProgressStatus.COMPLETED,
    )
    with pytest.raises((AttributeError, Exception)):
        event.to_status = DailyProgressStatus.BLOCKED  # type: ignore[misc]


def test_valid_transitions_table_covers_every_status() -> None:
    for status in DailyProgressStatus:
        assert status in VALID_TRANSITIONS


def test_coerce_daily_progress_status_accepts_enum_and_string() -> None:
    assert (
        coerce_daily_progress_status(DailyProgressStatus.COMPLETED)
        == DailyProgressStatus.COMPLETED
    )
    assert coerce_daily_progress_status("blocked") == DailyProgressStatus.BLOCKED


def test_is_reported_daily_progress_status_uses_domain_vocabulary() -> None:
    assert not is_reported_daily_progress_status(DailyProgressStatus.PENDING)
    assert is_reported_daily_progress_status("in_progress")
    assert is_reported_daily_progress_status(DailyProgressStatus.BLOCKED)


def test_is_completed_daily_progress_status_uses_domain_vocabulary() -> None:
    assert is_completed_daily_progress_status(DailyProgressStatus.COMPLETED)
    assert not is_completed_daily_progress_status("blocked")


def test_daily_progress_context_label_uses_domain_vocabulary() -> None:
    assert daily_progress_context_label(DailyProgressStatus.PENDING) == "not updated"
    assert daily_progress_context_label("in_progress") == "in progress"
    assert daily_progress_context_label(DailyProgressStatus.BLOCKED) == "blocked"
    assert daily_progress_context_label("completed") == "completed"
