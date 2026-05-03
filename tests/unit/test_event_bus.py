"""Unit tests for shared.services.event_bus.EventBus (Redis Streams)."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from shared.infra import event_bus as _event_bus_mod


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.xadd = AsyncMock(return_value="1234567890-0")
    r.xack = AsyncMock(return_value=1)
    r.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    r.xgroup_create = AsyncMock()
    r.xreadgroup = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
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


# ── subscribe / pending replay ───────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_claims_pending_before_reading_new_messages(
    bus, mock_redis, monkeypatch
):
    monkeypatch.setattr(_event_bus_mod.settings, "event_bus_pending_claim_idle_ms", 60_000)
    monkeypatch.setattr(_event_bus_mod.settings, "event_handler_timeout_seconds", 10)
    pending_event = _make_event()
    new_event = _make_event()
    stream_key = bus._get_stream_key("sync.completed")

    mock_redis.xautoclaim.side_effect = [
        ("0-0", [("100-0", {"data": pending_event.model_dump_json()})], []),
        ("0-0", [], []),
    ]
    mock_redis.xreadgroup = AsyncMock(
        return_value=[(stream_key, [("101-0", {"data": new_event.model_dump_json()})])]
    )

    subscription = bus.subscribe(["sync.completed"], timeout=1, group="qa-agent")
    first = await anext(subscription)
    second = await anext(subscription)
    await subscription.aclose()

    assert first.event_id == pending_event.event_id
    assert second.event_id == new_event.event_id
    mock_redis.xautoclaim.assert_any_await(
        stream_key,
        "qa-agent",
        mock_redis.xreadgroup.call_args.kwargs["consumername"],
        min_idle_time=60_000,
        start_id="0-0",
        count=10,
    )
    mock_redis.xack.assert_any_await(stream_key, "qa-agent", "100-0")


def test_pending_claim_idle_exceeds_handler_timeout(bus, monkeypatch):
    monkeypatch.setattr(_event_bus_mod.settings, "event_bus_pending_claim_idle_ms", 1_000)
    monkeypatch.setattr(_event_bus_mod.settings, "event_handler_timeout_seconds", 5)

    assert bus._pending_claim_idle_ms() == 6_000


def test_processing_lock_ttl_exceeds_handler_timeout(bus, monkeypatch):
    monkeypatch.setattr(_event_bus_mod.settings, "event_bus_processing_lock_ttl_seconds", 1)
    monkeypatch.setattr(_event_bus_mod.settings, "event_handler_timeout_seconds", 5)

    assert bus._processing_lock_ttl_seconds() == 65


@pytest.mark.asyncio
async def test_successful_event_is_marked_processed_before_ack(bus, mock_redis):
    event = _make_event()
    stream_key = bus._get_stream_key("sync.completed")
    generator = bus._yield_stream_results(
        [(stream_key, [("100-0", {"data": event.model_dump_json()})])],
        group="qa-agent",
        consumer="consumer-1",
    )

    received = await anext(generator)
    assert received.event_id == event.event_id

    with pytest.raises(StopAsyncIteration):
        await anext(generator)

    processed_key = f"projectcell:events:processed:qa-agent:{event.event_id}"
    processing_key = f"projectcell:events:processing:qa-agent:{event.event_id}"
    mock_redis.set.assert_has_awaits(
        [
            call(processing_key, "consumer-1", nx=True, ex=360),
            call(processed_key, "1", ex=604_800),
        ]
    )
    mock_redis.delete.assert_awaited_once_with(processing_key)
    mock_redis.xack.assert_awaited_once_with(stream_key, "qa-agent", "100-0")


@pytest.mark.asyncio
async def test_subscribe_skips_processed_duplicate_and_acks(bus, mock_redis):
    stream_key = bus._get_stream_key("sync.completed")
    duplicate_event = _make_event()
    next_event = _make_event()
    mock_redis.get.side_effect = ["1", None]
    mock_redis.xreadgroup = AsyncMock(
        return_value=[
            (
                stream_key,
                [
                    ("100-0", {"data": duplicate_event.model_dump_json()}),
                    ("101-0", {"data": next_event.model_dump_json()}),
                ],
            )
        ]
    )

    subscription = bus.subscribe(["sync.completed"], timeout=1, group="qa-agent")
    received = await anext(subscription)
    await subscription.aclose()

    assert received.event_id == next_event.event_id
    mock_redis.xack.assert_any_await(stream_key, "qa-agent", "100-0")
    assert mock_redis.set.await_count == 1


@pytest.mark.asyncio
async def test_subscribe_leaves_in_progress_duplicate_unacked(bus, mock_redis):
    stream_key = bus._get_stream_key("sync.completed")
    locked_event = _make_event()
    next_event = _make_event()
    mock_redis.set.side_effect = [False, True]
    mock_redis.xreadgroup = AsyncMock(
        return_value=[
            (
                stream_key,
                [
                    ("100-0", {"data": locked_event.model_dump_json()}),
                    ("101-0", {"data": next_event.model_dump_json()}),
                ],
            )
        ]
    )

    subscription = bus.subscribe(["sync.completed"], timeout=1, group="qa-agent")
    received = await anext(subscription)
    await subscription.aclose()

    assert received.event_id == next_event.event_id
    assert call(stream_key, "qa-agent", "100-0") not in mock_redis.xack.await_args_list


@pytest.mark.asyncio
async def test_subscribe_invalid_pending_message_goes_to_dlq(bus, mock_redis):
    stream_key = bus._get_stream_key("sync.completed")
    valid_event = _make_event()
    mock_redis.xautoclaim.side_effect = [
        ("0-0", [("100-0", {"data": "{bad-json"})], []),
        ("0-0", [], []),
    ]
    mock_redis.xreadgroup = AsyncMock(
        return_value=[(stream_key, [("101-0", {"data": valid_event.model_dump_json()})])]
    )

    subscription = bus.subscribe(["sync.completed"], timeout=1, group="qa-agent")
    received = await anext(subscription)
    await subscription.aclose()

    assert received.event_id == valid_event.event_id
    mock_redis.xack.assert_any_await(stream_key, "qa-agent", "100-0")
    dlq_call = mock_redis.xadd.call_args
    assert dlq_call.args[0] == "projectcell:events:dlq.failed"


@pytest.mark.asyncio
async def test_subscribe_creates_default_group_when_group_not_supplied(bus, mock_redis):
    stream_key = bus._get_stream_key("sync.completed")
    event = _make_event()
    mock_redis.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    mock_redis.xreadgroup = AsyncMock(
        return_value=[(stream_key, [("101-0", {"data": event.model_dump_json()})])]
    )

    subscription = bus.subscribe(["sync.completed"], timeout=1)
    received = await anext(subscription)
    await subscription.aclose()

    assert received.event_id == event.event_id
    mock_redis.xgroup_create.assert_awaited_once_with(
        stream_key,
        "default",
        id="0",
        mkstream=True,
    )
    assert mock_redis.xreadgroup.call_args.kwargs["groupname"] == "default"


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
