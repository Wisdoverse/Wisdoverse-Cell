"""Tests for outbox backlog observability helpers."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shared.observability import outbox


def test_oldest_pending_age_seconds_uses_oldest_created_at() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    rows = [
        SimpleNamespace(created_at=now - timedelta(seconds=10)),
        SimpleNamespace(created_at=now - timedelta(seconds=45)),
        SimpleNamespace(created_at=now - timedelta(seconds=20)),
    ]

    assert outbox.oldest_pending_age_seconds(rows, now=now) == 45.0


def test_oldest_pending_age_seconds_ignores_missing_timestamps() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert outbox.oldest_pending_age_seconds([SimpleNamespace()], now=now) == 0.0


def test_oldest_pending_age_seconds_handles_naive_timestamps() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    rows = [SimpleNamespace(created_at=datetime(2026, 5, 20, 11, 59, 30))]

    assert outbox.oldest_pending_age_seconds(rows, now=now) == 30.0


def test_record_outbox_pending_age_updates_gauge() -> None:
    rows = [SimpleNamespace(created_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC))]

    with patch.object(outbox, "oldest_pending_age_seconds", return_value=5.0), \
         patch.object(outbox, "OUTBOX_PENDING_OLDEST_AGE_SECONDS") as gauge:
        gauge_instance = MagicMock()
        gauge.labels.return_value = gauge_instance

        outbox.record_outbox_pending_age("requirement-manager", rows)

    gauge.labels.assert_called_once_with(runtime="requirement-manager")
    gauge_instance.set.assert_called_once_with(5.0)
