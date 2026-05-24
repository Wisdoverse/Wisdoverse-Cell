"""Lifecycle policy for Channel Gateway outbox records."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ChannelGatewayOutboxStatus(StrEnum):
    """Allowed persistence statuses for channel gateway outbox rows."""

    PENDING = "pending"
    PUBLISHED = "published"


class InvalidChannelGatewayOutboxTransitionError(ValueError):
    """Raised when a channel outbox row is moved through an illegal transition."""


@dataclass(frozen=True)
class ChannelGatewayOutboxLifecycle:
    """Guard retry and publish transitions for one channel outbox row."""

    event_id: str
    status: ChannelGatewayOutboxStatus
    attempts: int = 0
    last_error: str | None = None
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if self.attempts < 0:
            raise ValueError("attempts must not be negative")
        if self.status is ChannelGatewayOutboxStatus.PENDING and self.published_at is not None:
            raise ValueError("pending outbox rows must not have published_at")

    @classmethod
    def stage(cls, event_id: str) -> "ChannelGatewayOutboxLifecycle":
        """Create the initial lifecycle state for a newly staged event."""
        return cls(event_id=event_id, status=ChannelGatewayOutboxStatus.PENDING)

    @classmethod
    def from_record(cls, row: Any) -> "ChannelGatewayOutboxLifecycle":
        """Hydrate lifecycle state from an outbox persistence record."""
        return cls(
            event_id=str(row.event_id),
            status=ChannelGatewayOutboxStatus(str(row.status)),
            attempts=int(getattr(row, "attempts", 0) or 0),
            last_error=getattr(row, "last_error", None),
            published_at=getattr(row, "published_at", None),
        )

    def mark_published(
        self,
        *,
        now: datetime | None = None,
    ) -> "ChannelGatewayOutboxLifecycle":
        """Move a pending outbox row to published after a successful dispatch."""
        self._require_pending(ChannelGatewayOutboxStatus.PUBLISHED)
        return replace(
            self,
            status=ChannelGatewayOutboxStatus.PUBLISHED,
            attempts=self.attempts + 1,
            last_error=None,
            published_at=now or datetime.now(UTC),
        )

    def record_failure(self, error: str) -> "ChannelGatewayOutboxLifecycle":
        """Record a failed publish attempt while keeping the row retryable."""
        self._require_pending(ChannelGatewayOutboxStatus.PENDING)
        return replace(
            self,
            attempts=self.attempts + 1,
            last_error=error[:1000],
            published_at=None,
        )

    def to_update_values(self) -> dict[str, Any]:
        """Return SQLAlchemy update values for the guarded lifecycle state."""
        return {
            "status": self.status.value,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "published_at": self.published_at,
        }

    def _require_pending(self, target: ChannelGatewayOutboxStatus) -> None:
        if self.status is not ChannelGatewayOutboxStatus.PENDING:
            raise InvalidChannelGatewayOutboxTransitionError(
                f"cannot transition channel outbox event {self.event_id} "
                f"from {self.status.value} to {target.value}"
            )
