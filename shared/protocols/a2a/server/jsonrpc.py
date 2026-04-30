"""
A2A JSON-RPC Server

Handles JSON-RPC 2.0 requests for the A2A protocol.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models import (
    Message,
    MessageSendParams,
    Task,
    TaskCancelParams,
    TaskGetParams,
    TaskState,
)


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 Request."""

    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    id: str | int | None = Field(default=None, description="Request ID")
    method: str = Field(..., description="Method name")
    params: dict[str, Any] | None = Field(default=None, description="Method parameters")


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 Error."""

    model_config = ConfigDict(extra="forbid")

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Any | None = Field(default=None, description="Additional error data")


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 Response."""

    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    id: str | int | None = Field(default=None, description="Request ID")
    result: Any | None = Field(default=None, description="Result (on success)")
    error: JSONRPCError | None = Field(default=None, description="Error (on failure)")


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# A2A specific error codes (application-defined: -32000 to -32099)
TASK_NOT_FOUND = -32001
TASK_ALREADY_COMPLETED = -32002
UNAUTHORIZED = -32003
RATE_LIMITED = -32004


class A2ATaskStore:
    """In-memory task store for A2A tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._context_tasks: dict[str, list[str]] = {}  # context_id -> task_ids
        self._lock = asyncio.Lock()

    async def create_task(self, context_id: str | None = None) -> Task:
        """Create a new task."""
        async with self._lock:
            task = Task()
            if context_id:
                task.context_id = context_id
            self._tasks[task.id] = task
            if task.context_id not in self._context_tasks:
                self._context_tasks[task.context_id] = []
            self._context_tasks[task.context_id].append(task.id)
            return task

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    async def get_tasks_by_context(self, context_id: str) -> list[Task]:
        """Get all tasks in a context."""
        task_ids = self._context_tasks.get(context_id, [])
        return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    async def update_task(self, task: Task) -> None:
        """Update an existing task."""
        async with self._lock:
            self._tasks[task.id] = task

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        async with self._lock:
            if task_id not in self._tasks:
                return False
            task = self._tasks.pop(task_id)
            if task.context_id in self._context_tasks:
                self._context_tasks[task.context_id] = [
                    tid
                    for tid in self._context_tasks[task.context_id]
                    if tid != task_id
                ]
            return True


# Type for task handler functions
TaskHandler = Callable[[Task, Message], AsyncGenerator[Task, None]]


class A2AJSONRPCServer:
    """
    JSON-RPC 2.0 server for A2A protocol.

    Handles the following methods:
    - message/send: Send a message to create/continue a task
    - tasks/get: Get task details
    - tasks/cancel: Cancel a running task
    - tasks/pushNotification/set: Configure push notifications
    """

    def __init__(
        self,
        task_handler: TaskHandler | None = None,
        task_store: A2ATaskStore | None = None,
    ):
        self._task_handler = task_handler
        self._task_store = task_store or A2ATaskStore()
        self._push_configs: dict[str, dict] = {}  # task_id -> push config

    def set_task_handler(self, handler: TaskHandler) -> None:
        """Set the task handler for processing messages."""
        self._task_handler = handler

    async def handle_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a JSON-RPC request.

        Args:
            request_data: The parsed JSON-RPC request.

        Returns:
            JSON-RPC response dictionary.
        """
        try:
            request = JSONRPCRequest.model_validate(request_data)
        except Exception as e:
            return JSONRPCResponse(
                id=request_data.get("id"),
                error=JSONRPCError(
                    code=INVALID_REQUEST,
                    message=f"Invalid request: {e}",
                ),
            ).model_dump(exclude_none=True)

        # Dispatch to method handler
        method_handlers = {
            "message/send": self._handle_message_send,
            "tasks/get": self._handle_tasks_get,
            "tasks/cancel": self._handle_tasks_cancel,
            "tasks/pushNotification/set": self._handle_push_notification_set,
            "agent/getAuthenticatedExtendedCard": self._handle_get_extended_card,
        }

        handler = method_handlers.get(request.method)
        if handler is None:
            return JSONRPCResponse(
                id=request.id,
                error=JSONRPCError(
                    code=METHOD_NOT_FOUND,
                    message=f"Method not found: {request.method}",
                ),
            ).model_dump(exclude_none=True)

        try:
            result = await handler(request.params or {})
            return JSONRPCResponse(
                id=request.id,
                result=result,
            ).model_dump(exclude_none=True)
        except JSONRPCException as e:
            return JSONRPCResponse(
                id=request.id,
                error=JSONRPCError(
                    code=e.code,
                    message=e.message,
                    data=e.data,
                ),
            ).model_dump(exclude_none=True)
        except Exception as e:
            return JSONRPCResponse(
                id=request.id,
                error=JSONRPCError(
                    code=INTERNAL_ERROR,
                    message=f"Internal error: {e}",
                ),
            ).model_dump(exclude_none=True)

    async def handle_request_streaming(
        self, request_data: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Handle a JSON-RPC request with streaming response.

        Yields task updates as they occur.
        """
        try:
            request = JSONRPCRequest.model_validate(request_data)
        except Exception as e:
            yield JSONRPCResponse(
                id=request_data.get("id"),
                error=JSONRPCError(
                    code=INVALID_REQUEST,
                    message=f"Invalid request: {e}",
                ),
            ).model_dump(exclude_none=True)
            return

        if request.method != "message/send":
            # Non-streaming methods
            result = await self.handle_request(request_data)
            yield result
            return

        # Streaming message/send
        try:
            params = MessageSendParams.model_validate(request.params or {})
        except Exception as e:
            yield JSONRPCResponse(
                id=request.id,
                error=JSONRPCError(
                    code=INVALID_PARAMS,
                    message=f"Invalid params: {e}",
                ),
            ).model_dump(exclude_none=True)
            return

        # Create or get task
        task = await self._task_store.create_task(params.context_id)
        task.add_message(params.message)

        if self._task_handler is None:
            yield JSONRPCResponse(
                id=request.id,
                error=JSONRPCError(
                    code=INTERNAL_ERROR,
                    message="No task handler configured",
                ),
            ).model_dump(exclude_none=True)
            return

        # Stream task updates
        try:
            async for updated_task in self._task_handler(task, params.message):
                await self._task_store.update_task(updated_task)
                yield JSONRPCResponse(
                    id=request.id,
                    result=updated_task.model_dump(by_alias=True, exclude_none=True),
                ).model_dump(exclude_none=True)
        except Exception as e:
            task.update_status(TaskState.failed(str(e)))
            await self._task_store.update_task(task)
            yield JSONRPCResponse(
                id=request.id,
                error=JSONRPCError(
                    code=INTERNAL_ERROR,
                    message=f"Task handler error: {e}",
                ),
            ).model_dump(exclude_none=True)

    async def _handle_message_send(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle message/send method (non-streaming)."""
        try:
            send_params = MessageSendParams.model_validate(params)
        except Exception as e:
            raise JSONRPCException(INVALID_PARAMS, f"Invalid params: {e}")

        # Create or get task
        task = await self._task_store.create_task(send_params.context_id)
        task.add_message(send_params.message)

        if self._task_handler is None:
            raise JSONRPCException(INTERNAL_ERROR, "No task handler configured")

        # Process task (collect final result)
        final_task = task
        async for updated_task in self._task_handler(task, send_params.message):
            final_task = updated_task
            await self._task_store.update_task(updated_task)

        return final_task.model_dump(by_alias=True, exclude_none=True)

    async def _handle_tasks_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/get method."""
        try:
            get_params = TaskGetParams.model_validate(params)
        except Exception as e:
            raise JSONRPCException(INVALID_PARAMS, f"Invalid params: {e}")

        task = await self._task_store.get_task(get_params.task_id)
        if task is None:
            raise JSONRPCException(TASK_NOT_FOUND, f"Task not found: {get_params.task_id}")

        result = task.model_dump(by_alias=True, exclude_none=True)

        # Optionally limit history
        if get_params.history_length is not None and "history" in result:
            result["history"] = result["history"][-get_params.history_length :]

        return result

    async def _handle_tasks_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/cancel method."""
        try:
            cancel_params = TaskCancelParams.model_validate(params)
        except Exception as e:
            raise JSONRPCException(INVALID_PARAMS, f"Invalid params: {e}")

        task = await self._task_store.get_task(cancel_params.task_id)
        if task is None:
            raise JSONRPCException(
                TASK_NOT_FOUND, f"Task not found: {cancel_params.task_id}"
            )

        if task.is_terminal():
            raise JSONRPCException(
                TASK_ALREADY_COMPLETED,
                f"Task already in terminal state: {task.status.state}",
            )

        task.update_status(TaskState.canceled(cancel_params.reason))
        await self._task_store.update_task(task)

        return task.model_dump(by_alias=True, exclude_none=True)

    async def _handle_push_notification_set(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle tasks/pushNotification/set method."""
        task_id = params.get("taskId")
        if not task_id:
            raise JSONRPCException(INVALID_PARAMS, "taskId is required")

        task = await self._task_store.get_task(task_id)
        if task is None:
            raise JSONRPCException(TASK_NOT_FOUND, f"Task not found: {task_id}")

        # Store push notification config
        self._push_configs[task_id] = {
            "webhookUrl": params.get("webhookUrl"),
            "events": params.get("events", ["status_changed"]),
            "headers": params.get("headers", {}),
        }

        return {"success": True, "taskId": task_id}

    async def _handle_get_extended_card(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle agent/getAuthenticatedExtendedCard method."""
        # This should be overridden by the agent to return extended card
        raise JSONRPCException(
            METHOD_NOT_FOUND,
            "Extended card not available - override in agent implementation",
        )


class JSONRPCException(Exception):
    """Exception for JSON-RPC errors."""

    def __init__(
        self, code: int, message: str, data: Any | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
