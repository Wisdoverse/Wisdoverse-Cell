"""Tests for A2A JSON-RPC server."""

from collections.abc import AsyncGenerator

import pytest

from shared.protocols.a2a.models import (
    Message,
    Task,
    TaskState,
    TaskStatus,
)
from shared.protocols.a2a.server.jsonrpc import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    TASK_NOT_FOUND,
    A2AJSONRPCServer,
    A2ATaskStore,
)


class TestA2ATaskStore:
    """Tests for A2ATaskStore."""

    @pytest.fixture
    def store(self) -> A2ATaskStore:
        """Create a fresh task store."""
        return A2ATaskStore()

    @pytest.mark.asyncio
    async def test_create_task(self, store: A2ATaskStore):
        """Test creating a task."""
        task = await store.create_task()

        assert task.id.startswith("task_")
        assert task.context_id.startswith("ctx_")

    @pytest.mark.asyncio
    async def test_create_task_with_context(self, store: A2ATaskStore):
        """Test creating a task with existing context."""
        task = await store.create_task(context_id="ctx_existing")

        assert task.context_id == "ctx_existing"

    @pytest.mark.asyncio
    async def test_get_task(self, store: A2ATaskStore):
        """Test getting a task."""
        created = await store.create_task()
        retrieved = await store.get_task(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, store: A2ATaskStore):
        """Test getting a nonexistent task."""
        task = await store.get_task("nonexistent")
        assert task is None

    @pytest.mark.asyncio
    async def test_update_task(self, store: A2ATaskStore):
        """Test updating a task."""
        task = await store.create_task()
        task.update_status(TaskState.working("Processing..."))
        await store.update_task(task)

        retrieved = await store.get_task(task.id)
        assert retrieved.status.state == TaskStatus.WORKING

    @pytest.mark.asyncio
    async def test_delete_task(self, store: A2ATaskStore):
        """Test deleting a task."""
        task = await store.create_task()
        result = await store.delete_task(task.id)

        assert result is True
        assert await store.get_task(task.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_task(self, store: A2ATaskStore):
        """Test deleting a nonexistent task."""
        result = await store.delete_task("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_tasks_by_context(self, store: A2ATaskStore):
        """Test getting tasks by context."""
        context_id = "ctx_test"
        await store.create_task(context_id)
        await store.create_task(context_id)
        await store.create_task()  # Different context

        tasks = await store.get_tasks_by_context(context_id)

        assert len(tasks) == 2
        assert all(t.context_id == context_id for t in tasks)


class TestA2AJSONRPCServer:
    """Tests for A2AJSONRPCServer."""

    @pytest.fixture
    def server(self) -> A2AJSONRPCServer:
        """Create a server with a mock task handler."""

        async def mock_handler(task: Task, message: Message) -> AsyncGenerator[Task, None]:
            task.add_message(message)
            task.update_status(TaskState.working("Processing..."))
            yield task

            task.update_status(TaskState.completed("Done!"))
            yield task

        server = A2AJSONRPCServer()
        server.set_task_handler(mock_handler)
        return server

    @pytest.mark.asyncio
    async def test_invalid_request(self, server: A2AJSONRPCServer):
        """Test handling invalid JSON-RPC request."""
        response = await server.handle_request({"invalid": "request"})

        assert "error" in response
        assert response["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_method_not_found(self, server: A2AJSONRPCServer):
        """Test handling unknown method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "unknown/method",
        })

        assert "error" in response
        assert response["error"]["code"] == METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_message_send(self, server: A2AJSONRPCServer):
        """Test message/send method."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Hello!"}],
                }
            },
        })

        assert "result" in response
        assert response["result"]["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_message_send_invalid_params(self, server: A2AJSONRPCServer):
        """Test message/send with invalid params."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "invalid": "params",
            },
        })

        assert "error" in response
        assert response["error"]["code"] == INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_tasks_get(self, server: A2AJSONRPCServer):
        """Test tasks/get method."""
        # First create a task
        await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Create task"}],
                },
                "contextId": "test_context",
            },
        })

        # Get the task
        tasks = await server._task_store.get_tasks_by_context("test_context")
        assert len(tasks) > 0
        task_id = tasks[0].id

        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"taskId": task_id},
        })

        assert "result" in response
        assert response["result"]["id"] == task_id

    @pytest.mark.asyncio
    async def test_tasks_get_not_found(self, server: A2AJSONRPCServer):
        """Test tasks/get with nonexistent task."""
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tasks/get",
            "params": {"taskId": "nonexistent"},
        })

        assert "error" in response
        assert response["error"]["code"] == TASK_NOT_FOUND

    @pytest.mark.asyncio
    async def test_tasks_cancel(self, server: A2AJSONRPCServer):
        """Test tasks/cancel method."""
        # Create a task that stays in working state
        async def slow_handler(task: Task, message: Message) -> AsyncGenerator[Task, None]:
            task.update_status(TaskState.working("Processing..."))
            yield task
            # Never completes

        server.set_task_handler(slow_handler)

        # Create task
        create_response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Start"}],
                }
            },
        })

        task_id = create_response["result"]["id"]

        # Cancel it
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/cancel",
            "params": {
                "taskId": task_id,
                "reason": "Test cancellation",
            },
        })

        assert "result" in response
        assert response["result"]["status"]["state"] == "canceled"

    @pytest.mark.asyncio
    async def test_push_notification_set(self, server: A2AJSONRPCServer):
        """Test tasks/pushNotification/set method."""
        # First create a task
        create_response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Test"}],
                }
            },
        })

        task_id = create_response["result"]["id"]

        # Set push notification
        response = await server.handle_request({
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/pushNotification/set",
            "params": {
                "taskId": task_id,
                "webhookUrl": "https://example.com/webhook",
                "events": ["status_changed"],
            },
        })

        assert "result" in response
        assert response["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_streaming_response(self, server: A2AJSONRPCServer):
        """Test streaming response handling."""
        responses = []
        async for response in server.handle_request_streaming({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Stream test"}],
                }
            },
        }):
            responses.append(response)

        # Should have multiple updates
        assert len(responses) >= 2

        # First should be working, last should be completed
        states = [r["result"]["status"]["state"] for r in responses]
        assert "working" in states
        assert states[-1] == "completed"
