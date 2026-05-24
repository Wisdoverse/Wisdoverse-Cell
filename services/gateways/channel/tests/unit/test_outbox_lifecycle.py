"""Channel Gateway outbox lifecycle tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services.gateways.channel.core.outbox_lifecycle import (
    ChannelGatewayOutboxLifecycle,
    ChannelGatewayOutboxStatus,
    InvalidChannelGatewayOutboxTransitionError,
)


def test_channel_outbox_lifecycle_guards_publish_and_retry_transitions() -> None:
    staged = ChannelGatewayOutboxLifecycle.stage("evt_channel_01")

    failed = staged.record_failure("x" * 1200)
    published = failed.mark_published(now=datetime(2026, 5, 23, tzinfo=UTC))

    assert staged.status is ChannelGatewayOutboxStatus.PENDING
    assert failed.status is ChannelGatewayOutboxStatus.PENDING
    assert failed.attempts == 1
    assert failed.last_error == "x" * 1000
    assert published.status is ChannelGatewayOutboxStatus.PUBLISHED
    assert published.attempts == 2
    assert published.last_error is None
    assert published.published_at == datetime(2026, 5, 23, tzinfo=UTC)

    with pytest.raises(InvalidChannelGatewayOutboxTransitionError):
        published.record_failure("late failure")


def test_channel_outbox_lifecycle_hydrates_persistence_record() -> None:
    row = SimpleNamespace(
        event_id="evt_channel_02",
        status="pending",
        attempts=3,
        last_error="temporary network failure",
        published_at=None,
    )

    lifecycle = ChannelGatewayOutboxLifecycle.from_record(row)

    assert lifecycle.event_id == "evt_channel_02"
    assert lifecycle.status is ChannelGatewayOutboxStatus.PENDING
    assert lifecycle.attempts == 3
    assert lifecycle.to_update_values()["status"] == "pending"


def test_channel_outbox_lifecycle_rejects_invalid_persistence_state() -> None:
    row = SimpleNamespace(
        event_id="evt_channel_03",
        status="pending",
        attempts=-1,
        last_error=None,
        published_at=None,
    )

    with pytest.raises(ValueError):
        ChannelGatewayOutboxLifecycle.from_record(row)
