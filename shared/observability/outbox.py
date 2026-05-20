"""Outbox backlog observability helpers."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable

from shared.utils.logger import get_logger

from .metrics import OUTBOX_PENDING_OLDEST_AGE_SECONDS

logger = get_logger("observability.outbox")


def oldest_pending_age_seconds(
    rows: Iterable[Any],
    *,
    now: datetime | None = None,
) -> float:
    """Return the age of the oldest row with a ``created_at`` timestamp."""
    current = _as_aware_utc(now or datetime.now(UTC))
    oldest: datetime | None = None

    for row in rows:
        created_at = getattr(row, "created_at", None)
        if not isinstance(created_at, datetime):
            continue
        created_at = _as_aware_utc(created_at)
        if oldest is None or created_at < oldest:
            oldest = created_at

    if oldest is None:
        return 0.0
    return max(0.0, (current - oldest).total_seconds())


def record_outbox_pending_age(runtime: str, rows: Iterable[Any]) -> None:
    """Best-effort metric update for a runtime's oldest pending outbox row."""
    try:
        OUTBOX_PENDING_OLDEST_AGE_SECONDS.labels(runtime=runtime).set(
            oldest_pending_age_seconds(rows)
        )
    except Exception as exc:
        logger.debug(
            "outbox_pending_age_metric_failed",
            runtime=runtime,
            error=str(exc),
        )


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
