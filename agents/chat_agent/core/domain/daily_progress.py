"""Daily-progress aggregate for the chat-agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DailyProgressStatus(StrEnum):
    """Status values for one daily progress item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class InvalidDailyProgressTransitionError(ValueError):
    """Raised when a daily-progress status change is not allowed."""

    def __init__(
        self,
        *,
        progress_id: int | None,
        from_status: DailyProgressStatus,
        to_status: DailyProgressStatus,
    ) -> None:
        super().__init__(
            "illegal daily-progress transition "
            f"progress_id={progress_id} {from_status} -> {to_status}"
        )
        self.progress_id = progress_id
        self.from_status = from_status
        self.to_status = to_status


VALID_TRANSITIONS: dict[DailyProgressStatus, frozenset[DailyProgressStatus]] = {
    DailyProgressStatus.PENDING: frozenset(
        {
            DailyProgressStatus.IN_PROGRESS,
            DailyProgressStatus.BLOCKED,
            DailyProgressStatus.COMPLETED,
        }
    ),
    DailyProgressStatus.IN_PROGRESS: frozenset(
        {
            DailyProgressStatus.BLOCKED,
            DailyProgressStatus.COMPLETED,
        }
    ),
    DailyProgressStatus.BLOCKED: frozenset(
        {
            DailyProgressStatus.IN_PROGRESS,
            DailyProgressStatus.COMPLETED,
        }
    ),
    # A same-day correction can reopen a completed item without deleting
    # the historical note/raw reply stored on the record.
    DailyProgressStatus.COMPLETED: frozenset(
        {
            DailyProgressStatus.IN_PROGRESS,
            DailyProgressStatus.BLOCKED,
        }
    ),
}

_CONTEXT_LABELS: dict[DailyProgressStatus, str] = {
    DailyProgressStatus.PENDING: "not updated",
    DailyProgressStatus.IN_PROGRESS: "in progress",
    DailyProgressStatus.BLOCKED: "blocked",
    DailyProgressStatus.COMPLETED: "completed",
}


def coerce_daily_progress_status(
    value: DailyProgressStatus | str,
) -> DailyProgressStatus:
    """Normalize a persisted or inbound status into the domain enum."""
    if isinstance(value, DailyProgressStatus):
        return value
    try:
        return DailyProgressStatus(value)
    except ValueError as exc:
        allowed = ", ".join(status.value for status in DailyProgressStatus)
        raise ValueError(
            f"unknown daily-progress status {value!r}; must be one of {allowed}"
        ) from exc


def is_reported_daily_progress_status(value: DailyProgressStatus | str) -> bool:
    """Return whether a progress status has been updated by the user."""
    return coerce_daily_progress_status(value) != DailyProgressStatus.PENDING


def is_completed_daily_progress_status(value: DailyProgressStatus | str) -> bool:
    """Return whether a progress status is complete."""
    return coerce_daily_progress_status(value) == DailyProgressStatus.COMPLETED


def daily_progress_context_label(value: DailyProgressStatus | str) -> str:
    """Return the status label used in chat runtime context."""
    return _CONTEXT_LABELS[coerce_daily_progress_status(value)]


@dataclass(frozen=True, slots=True)
class DailyProgressStatusChanged:
    """In-memory domain event emitted when an item changes status."""

    progress_id: int | None
    user_id: str
    task_record_id: str
    from_status: DailyProgressStatus
    to_status: DailyProgressStatus


@dataclass(slots=True)
class DailyProgressEntry:
    """Aggregate root for one user's daily progress on one task."""

    progress_id: int | None
    user_id: str
    task_record_id: str
    task_title: str
    status: DailyProgressStatus | str = DailyProgressStatus.PENDING
    raw_reply: str = ""
    note: str = ""
    pending_events: list[DailyProgressStatusChanged] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("daily-progress entry requires user_id")
        self.status = coerce_daily_progress_status(self.status)

    @property
    def is_open(self) -> bool:
        """Return whether this entry still needs follow-up."""
        return self.status != DailyProgressStatus.COMPLETED

    @property
    def has_status_update(self) -> bool:
        """Return whether the user has reported any status for this entry."""
        return is_reported_daily_progress_status(self.status)

    def record_update(
        self,
        new_status: DailyProgressStatus | str,
        *,
        raw_reply: str = "",
        note: str = "",
    ) -> DailyProgressStatusChanged | None:
        """Apply a user progress update and emit an event if status changed."""
        target = coerce_daily_progress_status(new_status)
        event: DailyProgressStatusChanged | None = None
        if target != self.status:
            if target not in VALID_TRANSITIONS[self.status]:
                raise InvalidDailyProgressTransitionError(
                    progress_id=self.progress_id,
                    from_status=self.status,
                    to_status=target,
                )
            event = DailyProgressStatusChanged(
                progress_id=self.progress_id,
                user_id=self.user_id,
                task_record_id=self.task_record_id,
                from_status=self.status,
                to_status=target,
            )
            self.status = target
            self.pending_events.append(event)

        if raw_reply:
            self.raw_reply = raw_reply
        if note:
            self.note = note
        return event

    def pull_events(self) -> list[DailyProgressStatusChanged]:
        """Drain pending domain events, leaving the aggregate event buffer empty."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


__all__ = [
    "DailyProgressEntry",
    "DailyProgressStatus",
    "DailyProgressStatusChanged",
    "InvalidDailyProgressTransitionError",
    "VALID_TRANSITIONS",
    "coerce_daily_progress_status",
    "daily_progress_context_label",
    "is_completed_daily_progress_status",
    "is_reported_daily_progress_status",
]
