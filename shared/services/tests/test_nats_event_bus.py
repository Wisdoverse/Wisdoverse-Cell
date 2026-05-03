"""
Tests for NATSEventBus, EventBusProtocol, and EventBus factory.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.js.errors import NotFoundError

from shared import config as _config_mod
from shared.schemas.event import Event
from shared.services import nats_event_bus as _nats_mod
from shared.services.event_bus import EventBusProtocol
from shared.services.nats_event_bus import STREAM_NAME, SUBJECT_PREFIX, NATSEventBus


@pytest.fixture
def bus():
    return NATSEventBus(nats_url="nats://localhost:4222", consumer_name="test-consumer")


@pytest.fixture
def connected_bus(bus):
    """Bus with mocked JetStream context, ready for publish/subscribe."""
    mock_js = AsyncMock()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    bus._nc = mock_nc
    bus._js = mock_js
    return bus


# =============================================================================
# Protocol conformance
# =============================================================================

class TestEventBusProtocol:
    def test_nats_bus_satisfies_protocol(self):
        assert isinstance(NATSEventBus(nats_url="nats://localhost:4222"), EventBusProtocol)

    def test_redis_bus_satisfies_protocol(self):
        from shared.services.event_bus import EventBus
        assert isinstance(EventBus(), EventBusProtocol)


# =============================================================================
# is_connected property
# =============================================================================

class TestIsConnected:
    def test_is_connected_false_when_not_connected(self, bus):
        assert bus.is_connected is False

    def test_is_connected_true_when_nc_connected(self, bus):
        mock_nc = MagicMock()
        mock_nc.is_connected = True
        bus._nc = mock_nc
        assert bus.is_connected is True

    def test_is_connected_false_when_nc_disconnected(self, bus):
        mock_nc = MagicMock()
        mock_nc.is_connected = False
        bus._nc = mock_nc
        assert bus.is_connected is False


# =============================================================================
# connect()
# =============================================================================

class TestNATSEventBusConnect:
    @pytest.mark.asyncio
    async def test_connect_creates_stream_when_not_found(self, bus):
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_js.find_stream_info_by_subject.side_effect = NotFoundError
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch.object(_nats_mod.nats, "connect", return_value=mock_nc):
            await bus.connect()

        mock_js.add_stream.assert_awaited_once()
        config = mock_js.add_stream.call_args[0][0]
        assert config.name == STREAM_NAME
        assert f"{SUBJECT_PREFIX}.>" in config.subjects

    @pytest.mark.asyncio
    async def test_connect_reuses_existing_stream(self, bus):
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_js.find_stream_info_by_subject.return_value = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch.object(_nats_mod.nats, "connect", return_value=mock_nc):
            await bus.connect()

        mock_js.add_stream.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_connect_propagates_auth_error(self, bus):
        """Non-NotFoundError exceptions should propagate, not create stream."""
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_js.find_stream_info_by_subject.side_effect = PermissionError("no auth")
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch.object(_nats_mod.nats, "connect", return_value=mock_nc):
            with pytest.raises(PermissionError, match="no auth"):
                await bus.connect()

    @pytest.mark.asyncio
    async def test_connect_passes_multi_server_urls(self, bus):
        bus._nats_url = "nats://nats-1:4222,nats://nats-2:4222,nats://nats-3:4222"
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_js.find_stream_info_by_subject.return_value = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch.object(_nats_mod.nats, "connect", return_value=mock_nc) as mock_connect:
            await bus.connect()

        call_kwargs = mock_connect.call_args
        assert len(call_kwargs.kwargs["servers"]) == 3

    @pytest.mark.asyncio
    async def test_connect_registers_lifecycle_callbacks(self, bus):
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_js.find_stream_info_by_subject.return_value = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch.object(_nats_mod.nats, "connect", return_value=mock_nc) as mock_connect:
            await bus.connect()

        call_kwargs = mock_connect.call_args.kwargs
        assert call_kwargs["error_cb"] is not None
        assert call_kwargs["disconnected_cb"] is not None
        assert call_kwargs["reconnected_cb"] is not None
        assert call_kwargs["closed_cb"] is not None


# =============================================================================
# publish()
# =============================================================================

class TestNATSEventBusPublish:
    @pytest.mark.asyncio
    async def test_publish_serializes_event(self, connected_bus):
        mock_ack = MagicMock(seq=42)
        connected_bus._js.publish.return_value = mock_ack

        event = Event(
            event_id="evt_test123",
            event_type="requirement.confirmed",
            source_agent="test-agent",
            payload={"key": "value"},
        )
        result = await connected_bus.publish(event)

        assert result is True
        connected_bus._js.publish.assert_awaited_once()
        call_args = connected_bus._js.publish.call_args
        assert call_args[0][0] == f"{SUBJECT_PREFIX}.requirement.confirmed"
        assert b"evt_test123" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_publish_returns_false_on_error(self, connected_bus):
        connected_bus._js.publish.side_effect = Exception("connection lost")

        event = Event(
            event_id="evt_fail",
            event_type="requirement.confirmed",
            source_agent="test-agent",
            payload={},
        )
        result = await connected_bus.publish(event)
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_raises_when_not_connected(self, bus):
        event = Event(
            event_id="evt_noconn",
            event_type="requirement.confirmed",
            source_agent="test-agent",
            payload={},
        )
        with pytest.raises(RuntimeError, match="connect.*must be called"):
            await bus.publish(event)

    @pytest.mark.asyncio
    async def test_publish_returns_false_when_seq_zero(self, connected_bus):
        mock_ack = MagicMock(seq=0)
        connected_bus._js.publish.return_value = mock_ack

        event = Event(
            event_id="evt_dup",
            event_type="requirement.confirmed",
            source_agent="test-agent",
            payload={},
        )
        result = await connected_bus.publish(event)
        assert result is False


# =============================================================================
# subscribe()
# =============================================================================

class TestNATSEventBusSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_yields_parsed_events(self, connected_bus):
        event = Event(
            event_id="evt_sub1",
            event_type="requirement.confirmed",
            source_agent="test-agent",
            payload={"data": "test"},
        )
        mock_msg = MagicMock()
        mock_msg.data = event.model_dump_json().encode()
        mock_msg.subject = f"{SUBJECT_PREFIX}.requirement.confirmed"
        mock_msg.ack = AsyncMock()

        mock_sub = AsyncMock()
        # First fetch returns messages, second raises CancelledError to exit
        mock_sub.fetch = AsyncMock(side_effect=[[mock_msg], asyncio.CancelledError()])
        connected_bus._js.pull_subscribe = AsyncMock(return_value=mock_sub)

        events = []
        with pytest.raises(asyncio.CancelledError):
            async for evt in connected_bus.subscribe(["requirement.confirmed"]):
                events.append(evt)

        assert len(events) == 1
        assert events[0].event_id == "evt_sub1"
        mock_msg.ack.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subscribe_naks_on_parse_error(self, connected_bus):
        mock_msg = MagicMock()
        mock_msg.data = b"invalid json{{"
        mock_msg.subject = f"{SUBJECT_PREFIX}.requirement.confirmed"
        mock_msg.nak = AsyncMock()

        mock_sub = AsyncMock()
        mock_sub.fetch = AsyncMock(side_effect=[[mock_msg], asyncio.CancelledError()])
        connected_bus._js.pull_subscribe = AsyncMock(return_value=mock_sub)

        events = []
        with pytest.raises(asyncio.CancelledError):
            async for evt in connected_bus.subscribe(["requirement.confirmed"]):
                events.append(evt)

        assert len(events) == 0
        mock_msg.nak.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subscribe_continues_on_timeout(self, connected_bus):
        import nats.errors

        event = Event(
            event_id="evt_after_timeout",
            event_type="requirement.confirmed",
            source_agent="test-agent",
            payload={},
        )
        mock_msg = MagicMock()
        mock_msg.data = event.model_dump_json().encode()
        mock_msg.subject = f"{SUBJECT_PREFIX}.requirement.confirmed"
        mock_msg.ack = AsyncMock()

        mock_sub = AsyncMock()
        # Timeout first, then a message, then cancel
        mock_sub.fetch = AsyncMock(
            side_effect=[nats.errors.TimeoutError(), [mock_msg], asyncio.CancelledError()]
        )
        connected_bus._js.pull_subscribe = AsyncMock(return_value=mock_sub)

        events = []
        with pytest.raises(asyncio.CancelledError):
            async for evt in connected_bus.subscribe(["requirement.confirmed"]):
                events.append(evt)

        assert len(events) == 1
        assert events[0].event_id == "evt_after_timeout"

    @pytest.mark.asyncio
    async def test_subscribe_raises_when_not_connected(self, bus):
        with pytest.raises(RuntimeError, match="connect.*must be called"):
            async for _ in bus.subscribe(["requirement.confirmed"]):
                pass


# =============================================================================
# disconnect()
# =============================================================================


class TestNATSEventBusDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self, bus):
        mock_nc = AsyncMock()
        mock_nc.is_closed = False
        bus._nc = mock_nc

        await bus.disconnect()

        mock_nc.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_already_closed(self, bus):
        mock_nc = AsyncMock()
        mock_nc.is_closed = True
        bus._nc = mock_nc

        await bus.disconnect()

        mock_nc.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_no_connection(self, bus):
        await bus.disconnect()  # Should not raise


# =============================================================================
# get_queue_length / get_all_queue_lengths
# =============================================================================

class TestNATSEventBusQueueLength:
    @pytest.mark.asyncio
    async def test_get_queue_length_returns_pending(self, connected_bus):
        mock_info = MagicMock(num_pending=15)
        connected_bus._js.consumer_info.return_value = mock_info

        result = await connected_bus.get_queue_length("requirement.confirmed")
        assert result == 15

    @pytest.mark.asyncio
    async def test_get_queue_length_returns_negative_on_error(self, connected_bus):
        connected_bus._js.consumer_info.side_effect = Exception("consumer not found")

        result = await connected_bus.get_queue_length("requirement.confirmed")
        assert result == -1

    @pytest.mark.asyncio
    async def test_get_queue_length_returns_negative_when_not_connected(self, bus):
        result = await bus.get_queue_length("requirement.confirmed")
        assert result == -1

    @pytest.mark.asyncio
    async def test_get_all_queue_lengths(self, connected_bus):
        mock_info = MagicMock(num_pending=10, num_redelivered=2)
        connected_bus._js.consumer_info.return_value = mock_info

        result = await connected_bus.get_all_queue_lengths()
        assert result == {"pending": 10, "redelivered": 2}

    @pytest.mark.asyncio
    async def test_get_all_queue_lengths_returns_empty_on_error(self, connected_bus):
        connected_bus._js.consumer_info.side_effect = Exception("fail")

        result = await connected_bus.get_all_queue_lengths()
        assert result == {}


# =============================================================================
# Factory
# =============================================================================


class TestEventBusFactory:
    def test_factory_creates_redis_by_default(self):
        from shared.services.event_bus import EventBus, create_event_bus

        with patch.object(_config_mod, "settings") as mock_settings:
            mock_settings.event_bus_backend = "redis"
            mock_settings.redis_url = "redis://localhost:6379/0"

            bus = create_event_bus()
            assert isinstance(bus, EventBus)

    def test_factory_creates_nats_when_configured(self):
        from shared.services.event_bus import create_event_bus

        with patch.object(_config_mod, "settings") as mock_settings:
            mock_settings.event_bus_backend = "nats"
            mock_settings.nats_url = "nats://localhost:4222"
            mock_settings.event_bus_consumer_name = ""
            mock_settings.otel_service_name = "ai-core"

            bus = create_event_bus()
            assert isinstance(bus, NATSEventBus)
            assert bus._consumer_name == "ai-core"

    def test_factory_uses_configured_nats_consumer_name(self):
        from shared.services.event_bus import create_event_bus

        with patch.object(_config_mod, "settings") as mock_settings:
            mock_settings.event_bus_backend = "nats"
            mock_settings.nats_url = "nats://localhost:4222"
            mock_settings.event_bus_consumer_name = "qa-agent"
            mock_settings.otel_service_name = "ai-core"

            bus = create_event_bus()
            assert isinstance(bus, NATSEventBus)
            assert bus._consumer_name == "qa-agent"

    def test_factory_override_backend_parameter(self):
        from shared.services.event_bus import create_event_bus

        with patch.object(_config_mod, "settings") as mock_settings:
            mock_settings.event_bus_backend = "redis"
            mock_settings.nats_url = "nats://localhost:4222"
            mock_settings.event_bus_consumer_name = ""
            mock_settings.otel_service_name = "pjm-agent"

            bus = create_event_bus(backend="nats")
            assert isinstance(bus, NATSEventBus)
            assert bus._consumer_name == "pjm-agent"

    def test_factory_raises_on_unknown_backend(self):
        from shared.services.event_bus import create_event_bus

        with patch.object(_config_mod, "settings") as mock_settings:
            mock_settings.event_bus_backend = "kafka"
            with pytest.raises(ValueError, match="Unknown EVENT_BUS_BACKEND"):
                create_event_bus()

    def test_factory_normalizes_case_and_whitespace(self):
        from shared.services.event_bus import create_event_bus

        with patch.object(_config_mod, "settings") as mock_settings:
            mock_settings.nats_url = "nats://localhost:4222"
            mock_settings.event_bus_consumer_name = ""
            mock_settings.otel_service_name = "ai-core"

            bus = create_event_bus(backend=" NATS ")
            assert isinstance(bus, NATSEventBus)
