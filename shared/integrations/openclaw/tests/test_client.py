"""
Tests for OpenClawClient

Tests:
1. Handshake protocol
2. JSON-RPC request/response matching
3. Event dispatching
4. Disconnect and cleanup
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from shared.integrations.openclaw.client import OpenClawClient


@pytest.fixture
def client() -> OpenClawClient:
    return OpenClawClient(
        gateway_url="ws://127.0.0.1:18789",
        device_id="test-device",
        auth_token="test-token",
    )


class TestClientInit:
    """Test client initialization."""

    def test_defaults(self) -> None:
        c = OpenClawClient()
        assert c._gateway_url == "ws://127.0.0.1:18789"
        assert c._device_id == "wisdoverse-cell"
        assert c._auth_token == ""
        assert c.connected is False

    def test_custom_params(self, client: OpenClawClient) -> None:
        assert client._gateway_url == "ws://127.0.0.1:18789"
        assert client._device_id == "test-device"
        assert client._auth_token == "test-token"


class TestEventRegistration:
    """Test event handler registration."""

    def test_on_event_adds_handler(self, client: OpenClawClient) -> None:
        handler = AsyncMock()
        client.on_event(handler)
        assert handler in client._event_handlers

    def test_multiple_handlers(self, client: OpenClawClient) -> None:
        h1 = AsyncMock()
        h2 = AsyncMock()
        client.on_event(h1)
        client.on_event(h2)
        assert len(client._event_handlers) == 2


class TestSendRequest:
    """Test JSON-RPC request sending."""

    @pytest.mark.asyncio
    async def test_send_request_not_connected_raises(
        self, client: OpenClawClient
    ) -> None:
        with pytest.raises(ConnectionError):
            await client.send_request("test.method")

    @pytest.mark.asyncio
    async def test_send_notification_not_connected_raises(
        self, client: OpenClawClient
    ) -> None:
        with pytest.raises(ConnectionError):
            await client.send_notification("test.method")


class TestHandleResponse:
    """Test JSON-RPC response handling."""

    def test_handle_response_resolves_future(self, client: OpenClawClient) -> None:
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        client._pending[42] = future

        client._handle_response({"id": 42, "result": {"ok": True}})

        assert future.done()
        assert future.result() == {"ok": True}
        assert 42 not in client._pending
        loop.close()

    def test_handle_response_error(self, client: OpenClawClient) -> None:
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        client._pending[43] = future

        client._handle_response({
            "id": 43,
            "error": {"code": -32600, "message": "Invalid request"},
        })

        assert future.done()
        with pytest.raises(RuntimeError, match="RPC error"):
            future.result()
        loop.close()

    def test_handle_response_unknown_id_ignored(self, client: OpenClawClient) -> None:
        # Should not raise
        client._handle_response({"id": 999, "result": {}})


class TestHandleEvent:
    """Test event dispatching."""

    @pytest.mark.asyncio
    async def test_dispatches_to_handlers(self, client: OpenClawClient) -> None:
        handler = AsyncMock()
        client.on_event(handler)

        await client._handle_event({
            "method": "channel.message",
            "params": {"content": "hello"},
        })

        handler.assert_called_once_with("channel.message", {"content": "hello"})

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_stop_others(
        self, client: OpenClawClient
    ) -> None:
        bad_handler = AsyncMock(side_effect=ValueError("oops"))
        good_handler = AsyncMock()
        client.on_event(bad_handler)
        client.on_event(good_handler)

        await client._handle_event({"method": "test", "params": {}})

        bad_handler.assert_called_once()
        good_handler.assert_called_once()


class TestDisconnect:
    """Test disconnect behavior."""

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self, client: OpenClawClient) -> None:
        mock_ws = AsyncMock()
        client._ws = mock_ws
        client._connected = True
        client._receive_task = None

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        client._pending[1] = future

        await client.disconnect()

        assert client._connected is False
        assert client._ws is None
        assert len(client._pending) == 0
        mock_ws.close.assert_called_once()
