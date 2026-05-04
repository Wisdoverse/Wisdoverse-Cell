"""
OpenClawClient - OpenClaw Gateway WebSocket client

Connects to OpenClaw Gateway over WebSocket and communicates with JSON-RPC.
Supports automatic reconnects, device handshake authentication, and event callbacks.
"""
import asyncio
import json
from typing import Any, Callable, Coroutine, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from shared.utils.logger import get_logger

logger = get_logger("openclaw.client")

EventHandler = Callable[[str, dict], Coroutine[Any, Any, None]]


class OpenClawClient:
    """
    OpenClaw Gateway WebSocket client.

    Usage:
        client = OpenClawClient(
            gateway_url="ws://127.0.0.1:18789",
            device_id="projectcell-001",
            auth_token="secret",
        )
        client.on_event(handle_event)
        await client.connect()
    """

    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:18789",
        device_id: str = "projectcell",
        auth_token: str = "",
        reconnect_max_delay: float = 60.0,
    ):
        self._gateway_url = gateway_url
        self._device_id = device_id
        self._auth_token = auth_token
        self._reconnect_max_delay = reconnect_max_delay

        self._ws: Optional[ClientConnection] = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._event_handlers: list[EventHandler] = []
        self._connected = False
        self._receive_task: Optional[asyncio.Task[None]] = None
        self._closing = False

    @property
    def connected(self) -> bool:
        return self._connected

    def on_event(self, handler: EventHandler) -> None:
        """Register an event handler callback."""
        self._event_handlers.append(handler)

    async def connect(self) -> None:
        """Connect to OpenClaw Gateway and complete the handshake."""
        self._closing = False
        delay = 1.0

        while not self._closing:
            try:
                self._ws = await websockets.connect(self._gateway_url)
                await self._handshake()
                self._connected = True
                delay = 1.0
                logger.info("openclaw_connected", gateway=self._gateway_url)

                self._receive_task = asyncio.create_task(self._receive_loop())
                await self._receive_task
            except asyncio.CancelledError:
                break
            except Exception:
                self._connected = False
                if self._closing:
                    break
                logger.warning(
                    "openclaw_reconnecting",
                    delay=delay,
                    gateway=self._gateway_url,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._reconnect_max_delay)

    async def disconnect(self) -> None:
        """Disconnect from OpenClaw Gateway."""
        self._closing = True
        self._connected = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        # Cancel all pending requests
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        logger.info("openclaw_disconnected")

    async def send_request(
        self,
        method: str,
        params: Optional[dict] = None,
        timeout: float = 30.0,
    ) -> dict:
        """
        Send a JSON-RPC request and wait for the response.

        Args:
            method: RPC method name.
            params: Parameter dictionary.
            timeout: Timeout in seconds.

        Returns:
            Response result dictionary.

        Raises:
            ConnectionError: The client is not connected.
            TimeoutError: The request timed out.
            RuntimeError: The RPC returned an error.
        """
        if not self._ws or not self._connected:
            raise ConnectionError("Not connected to OpenClaw Gateway")

        self._request_id += 1
        request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._ws.send(json.dumps(message))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise TimeoutError(f"RPC request '{method}' timed out after {timeout}s")
        except Exception:
            self._pending.pop(request_id, None)
            raise

    async def send_notification(self, method: str, params: Optional[dict] = None) -> None:
        """
        Send a JSON-RPC notification without waiting for a response.

        Args:
            method: RPC method name.
            params: Parameter dictionary.
        """
        if not self._ws or not self._connected:
            raise ConnectionError("Not connected to OpenClaw Gateway")

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params

        await self._ws.send(json.dumps(message))

    # === Private Methods ===

    async def _handshake(self) -> None:
        """Complete the OpenClaw Gateway handshake."""
        assert self._ws is not None

        handshake = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "connect",
            "params": {
                "device_id": self._device_id,
                "token": self._auth_token,
                "client_type": "projectcell",
                "capabilities": ["channel", "tools"],
            },
        }
        await self._ws.send(json.dumps(handshake))

        raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        response = json.loads(raw)

        if "error" in response:
            error = response["error"]
            raise RuntimeError(
                f"Handshake failed: [{error.get('code', -1)}] {error.get('message', 'unknown')}"
            )

        logger.info("openclaw_handshake_ok", device_id=self._device_id)

    async def _receive_loop(self) -> None:
        """Receive and dispatch incoming WebSocket messages."""
        assert self._ws is not None

        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "openclaw_invalid_json",
                        raw_length=len(str(raw)),
                    )
                    continue

                if "id" in msg and msg["id"] in self._pending:
                    self._handle_response(msg)
                elif "method" in msg and "id" not in msg:
                    await self._handle_event(msg)
                elif "method" in msg and "id" in msg:
                    await self._handle_event(msg)
        except websockets.ConnectionClosed:
            logger.info("openclaw_connection_closed")
        finally:
            self._connected = False

    def _handle_response(self, msg: dict) -> None:
        """Handle a JSON-RPC response."""
        request_id = msg["id"]
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return

        if "error" in msg:
            error = msg["error"]
            future.set_exception(
                RuntimeError(
                    f"RPC error: [{error.get('code', -1)}] {error.get('message', 'unknown')}"
                )
            )
        else:
            future.set_result(msg.get("result", {}))

    async def _handle_event(self, msg: dict) -> None:
        """Dispatch an OpenClaw event to registered handlers."""
        method = msg.get("method", "")
        params = msg.get("params", {})

        for handler in self._event_handlers:
            try:
                await handler(method, params)
            except Exception:
                logger.exception("openclaw_event_handler_error", method=method)
