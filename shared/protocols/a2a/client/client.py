"""
A2A Client

Async HTTP client for communicating with A2A agents.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..models import AgentCard, Message, MessageSendParams, Task, TaskGetParams


class A2AClientConfig(BaseModel):
    """Configuration for A2A client."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(..., description="Base URL of the A2A agent")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")
    auth_token: str | None = Field(default=None, description="Bearer token for authentication")
    api_key: str | None = Field(default=None, description="API key for authentication")
    api_key_header: str = Field(default="X-API-Key", description="Header name for API key")


class A2AClient:
    """
    Async client for A2A protocol communication.

    Supports:
    - Agent card discovery
    - Sending messages (with optional streaming)
    - Getting task status
    - Canceling tasks
    - SSE streaming for task updates
    """

    def __init__(self, config: A2AClientConfig):
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._agent_card: AgentCard | None = None

    async def __aenter__(self) -> "A2AClient":
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        headers = {}
        if self._config.auth_token:
            headers["Authorization"] = f"Bearer {self._config.auth_token}"
        if self._config.api_key:
            headers[self._config.api_key_header] = self._config.api_key

        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            headers=headers,
        )

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_connected(self) -> httpx.AsyncClient:
        """Ensure client is connected."""
        if self._client is None:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        client = self._ensure_connected()
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries):
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise
                last_error = e
            except httpx.RequestError as e:
                last_error = e

            if attempt < self._config.max_retries - 1:
                await asyncio.sleep(self._config.retry_delay * (attempt + 1))

        raise last_error or RuntimeError("Request failed")

    # ============ Discovery ============

    async def discover(self) -> AgentCard:
        """
        Discover the agent by fetching its Agent Card.

        Returns:
            The agent's AgentCard.
        """
        response = await self._request_with_retry(
            "GET",
            "/.well-known/agent.json",
        )
        data = response.json()
        self._agent_card = AgentCard.model_validate(data)
        return self._agent_card

    @property
    def agent_card(self) -> AgentCard | None:
        """Get the cached agent card."""
        return self._agent_card

    # ============ JSON-RPC Methods ============

    async def _jsonrpc_call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Make a JSON-RPC call."""
        request = {
            "jsonrpc": "2.0",
            "id": request_id or "1",
            "method": method,
            "params": params or {},
        }

        response = await self._request_with_retry(
            "POST",
            "/a2a/rpc",
            json=request,
        )
        result = response.json()

        if "error" in result and result["error"]:
            error = result["error"]
            raise A2AError(
                code=error.get("code", -1),
                message=error.get("message", "Unknown error"),
                data=error.get("data"),
            )

        return result.get("result", {})

    async def send_message(
        self,
        message: Message,
        context_id: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> Task:
        """
        Send a message to the agent.

        Args:
            message: The message to send.
            context_id: Optional context ID to continue a conversation.
            configuration: Optional configuration for the task.

        Returns:
            The created or updated Task.
        """
        params = MessageSendParams(
            message=message,
            context_id=context_id,  # type: ignore[call-arg]
            configuration=configuration or {},
        )

        result = await self._jsonrpc_call(
            "message/send",
            params.model_dump(by_alias=True, exclude_none=True),
        )

        return Task.model_validate(result)

    async def send_message_streaming(
        self,
        message: Message,
        context_id: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Task, None]:
        """
        Send a message with streaming response.

        Args:
            message: The message to send.
            context_id: Optional context ID to continue a conversation.
            configuration: Optional configuration for the task.

        Yields:
            Task updates as they occur.
        """
        client = self._ensure_connected()

        params = MessageSendParams(
            message=message,
            context_id=context_id,  # type: ignore[call-arg]
            configuration=configuration or {},
        )

        request = {
            "jsonrpc": "2.0",
            "id": "stream",
            "method": "message/send",
            "params": params.model_dump(by_alias=True, exclude_none=True),
        }

        async with client.stream(
            "POST",
            "/a2a/rpc/stream",
            json=request,
        ) as response:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data = line[6:]  # Remove "data: " prefix
                if data == "[DONE]":
                    break

                try:
                    result = json.loads(data)
                    if "error" in result and result["error"]:
                        error = result["error"]
                        raise A2AError(
                            code=error.get("code", -1),
                            message=error.get("message", "Unknown error"),
                            data=error.get("data"),
                        )
                    if "result" in result:
                        yield Task.model_validate(result["result"])
                except json.JSONDecodeError:
                    continue

    async def get_task(
        self,
        task_id: str,
        history_length: int | None = None,
    ) -> Task:
        """
        Get task details.

        Args:
            task_id: The task ID to retrieve.
            history_length: Optional limit on history messages.

        Returns:
            The Task with current state.
        """
        params = TaskGetParams(
            task_id=task_id,  # type: ignore[call-arg]
            history_length=history_length,  # type: ignore[call-arg]
        )

        result = await self._jsonrpc_call(
            "tasks/get",
            params.model_dump(by_alias=True, exclude_none=True),
        )

        return Task.model_validate(result)

    async def cancel_task(
        self,
        task_id: str,
        reason: str | None = None,
    ) -> Task:
        """
        Cancel a running task.

        Args:
            task_id: The task ID to cancel.
            reason: Optional cancellation reason.

        Returns:
            The canceled Task.
        """
        result = await self._jsonrpc_call(
            "tasks/cancel",
            {"taskId": task_id, "reason": reason},
        )

        return Task.model_validate(result)

    async def set_push_notification(
        self,
        task_id: str,
        webhook_url: str,
        events: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Configure push notifications for a task.

        Args:
            task_id: The task ID.
            webhook_url: URL to receive notifications.
            events: Events to notify on (default: ["status_changed"]).
            headers: Custom headers for webhook requests.

        Returns:
            Configuration result.
        """
        return await self._jsonrpc_call(
            "tasks/pushNotification/set",
            {
                "taskId": task_id,
                "webhookUrl": webhook_url,
                "events": events or ["status_changed"],
                "headers": headers or {},
            },
        )

    # ============ SSE Streaming ============

    async def stream_task_status(
        self,
        task_id: str,
    ) -> AsyncGenerator[Task, None]:
        """
        Stream task status updates via SSE.

        Args:
            task_id: The task ID to monitor.

        Yields:
            Task updates as they occur.
        """
        client = self._ensure_connected()

        async with client.stream(
            "GET",
            f"/a2a/tasks/{task_id}/stream",
        ) as response:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data = line[6:]
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                    if event.get("type") == "status" and "task" in event:
                        yield Task.model_validate(event["task"])
                    elif event.get("type") == "deleted":
                        break
                except json.JSONDecodeError:
                    continue

    # ============ Convenience Methods ============

    async def ask(
        self,
        text: str,
        context_id: str | None = None,
    ) -> Task:
        """
        Send a simple text message and wait for completion.

        Args:
            text: The text message to send.
            context_id: Optional context ID.

        Returns:
            The completed Task.
        """
        message = Message.text(text, role="user")
        return await self.send_message(message, context_id)

    async def ask_streaming(
        self,
        text: str,
        context_id: str | None = None,
    ) -> AsyncGenerator[Task, None]:
        """
        Send a simple text message with streaming response.

        Args:
            text: The text message to send.
            context_id: Optional context ID.

        Yields:
            Task updates as they occur.
        """
        message = Message.text(text, role="user")
        async for task in self.send_message_streaming(message, context_id):
            yield task


class A2AError(Exception):
    """Exception for A2A protocol errors."""

    def __init__(
        self,
        code: int,
        message: str,
        data: Any | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def __str__(self) -> str:
        return f"A2AError({self.code}): {self.message}"


async def discover_agent(url: str) -> AgentCard:
    """
    Convenience function to discover an agent.

    Args:
        url: Base URL of the agent.

    Returns:
        The agent's AgentCard.
    """
    config = A2AClientConfig(base_url=url)
    async with A2AClient(config) as client:
        return await client.discover()
