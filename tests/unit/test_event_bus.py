"""Unit tests for shared.services.event_bus.EventBus (Redis Streams)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.infra import event_bus as _event_bus_mod


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.xadd = AsyncMock(return_value="1234567890-0")
    r.xlen = AsyncMock(return_value=0)
    r.xpending = AsyncMock(return_value={"pending": 0})
    r.xrevrange = AsyncMock(return_value=[])
    r.close = AsyncMock()
    return r


@pytest.fixture
def bus(mock_redis):
    with patch.object(_event_bus_mod, "create_event_bus"):
        from shared.infra.event_bus import EventBus

    b = EventBus(redis_url="redis://:secret@localhost:6379/0")
    b._redis = mock_redis  # skip actual connect
    return b


def _make_event():
    with patch.object(_event_bus_mod, "create_event_bus"):
        from shared.schemas.event import Event

    return Event.create(
        event_type="sync.completed",
        source_agent="test",
        payload={"k": "v"},
    )


# ── _safe_url ────────────────────────────────────────────────────────

def test_safe_url_masks_password(bus):
    result = bus._safe_url("redis://:secret@host:6379/0")
    assert result == "redis://:***@host:6379/0"
    assert "secret" not in result


def test_safe_url_no_password(bus):
    url = "redis://host:6379/0"
    assert bus._safe_url(url) == url


# ── _get_stream_key ─────────────────────────────────────────────────

def test_get_stream_key(bus):
    """Stream key is always {prefix}:{event_type} — no group suffix."""
    result = bus._get_stream_key("sync.completed")
    assert result == "projectcell:events:sync.completed"


# ── publish ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_calls_xadd(bus, mock_redis):
    event = _make_event()

    result = await bus.publish(event)

    assert result is True
    mock_redis.xadd.assert_awaited_once()
    call_args = mock_redis.xadd.call_args
    # First arg is stream key
    assert call_args.args[0] == "projectcell:events:sync.completed"
    # Second arg is field dict with "data" key
    assert "data" in call_args.args[1]


@pytest.mark.asyncio
async def test_publish_uses_approximate_maxlen(bus, mock_redis):
    event = _make_event()

    await bus.publish(event)

    call_kwargs = mock_redis.xadd.call_args.kwargs
    assert call_kwargs.get("approximate") is True
    assert "maxlen" in call_kwargs


@pytest.mark.asyncio
async def test_publish_returns_false_on_error(bus, mock_redis):
    mock_redis.xadd = AsyncMock(side_effect=ConnectionError("Redis down"))
    event = _make_event()

    result = await bus.publish(event)

    assert result is False


# ── dead letter queue ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_dlq_writes_observable_failed_event(bus, mock_redis):
    event = _make_event()
    event.metadata.trace_id = "trace_dlq"

    await bus.publish_dlq(event, "handler exploded", "analysis-agent")

    mock_redis.xadd.assert_awaited_once()
    call_args = mock_redis.xadd.call_args
    assert call_args.args[0] == "projectcell:events:dlq.failed"

    from shared.schemas.event import Event

    dlq_event = Event.model_validate_json(call_args.args[1]["data"])
    assert dlq_event.event_type == "dlq.failed"
    assert dlq_event.source_agent == "analysis-agent"
    assert dlq_event.metadata.trace_id == "trace_dlq"
    assert dlq_event.payload["original_event_id"] == event.event_id
    assert dlq_event.payload["failed_by_agent"] == "analysis-agent"
    assert dlq_event.payload["failure_stage"] == "handler"
    assert dlq_event.payload["error"] == "handler exploded"


@pytest.mark.asyncio
async def test_publish_raw_dlq_writes_validation_failure(bus, mock_redis):
    await bus.publish_raw_dlq(
        raw_event_data="{bad-json",
        error="validation failed",
        agent_id="requirement-manager",
    )

    call_args = mock_redis.xadd.call_args
    assert call_args.args[0] == "projectcell:events:dlq.failed"

    from shared.schemas.event import Event

    dlq_event = Event.model_validate_json(call_args.args[1]["data"])
    assert dlq_event.payload["original_event_id"] is None
    assert dlq_event.payload["failure_stage"] == "validation"
    assert dlq_event.payload["original_payload"] == {"raw_event_data": "{bad-json"}


@pytest.mark.asyncio
async def test_get_dead_letter_count_uses_dlq_stream(bus, mock_redis):
    mock_redis.xlen = AsyncMock(return_value=2)

    result = await bus.get_dead_letter_count()

    assert result == 2
    mock_redis.xlen.assert_awaited_once_with("projectcell:events:dlq.failed")


@pytest.mark.asyncio
async def test_list_dead_letters_returns_recent_events(bus, mock_redis):
    event = _make_event()
    await bus.publish_dlq(event, "timeout", "qa-agent")
    dlq_data = mock_redis.xadd.call_args.args[1]["data"]
    mock_redis.xrevrange = AsyncMock(return_value=[("123-0", {"data": dlq_data})])

    events = await bus.list_dead_letters(limit=25)

    assert len(events) == 1
    assert events[0].event_type == "dlq.failed"
    assert events[0].payload["failed_by_agent"] == "qa-agent"
    mock_redis.xrevrange.assert_awaited_once_with(
        "projectcell:events:dlq.failed",
        count=25,
    )


# ── disconnect ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disconnect_closes_redis(bus, mock_redis):
    await bus.disconnect()

    mock_redis.close.assert_awaited_once()
    assert bus._redis is None


# ── connect ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_uses_masked_url_in_log():
    with patch.object(_event_bus_mod, "create_event_bus"):
        from shared.infra.event_bus import EventBus

    with patch.object(_event_bus_mod, "redis") as mock_redis_mod, \
         patch.object(_event_bus_mod, "logger") as mock_logger:
        mock_redis_mod.from_url = MagicMock(return_value=AsyncMock())
        b = EventBus(redis_url="redis://:supersecret@myhost:6379/0")
        await b.connect()

        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args.kwargs
        assert "supersecret" not in call_kwargs.get("redis_url", "")
        assert "***" in call_kwargs.get("redis_url", "")
