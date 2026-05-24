"""Tests for chat-agent internal request API."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agents.chat_agent.api.requests import router


@pytest.mark.asyncio
async def test_request_endpoint_delegates_to_chat_agent_runtime() -> None:
    agent = SimpleNamespace(handle_request=AsyncMock(return_value={"reply": "ok"}))
    app = FastAPI()
    app.state.runtime = SimpleNamespace(agent=agent)
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat-agent/requests",
            json={"action": "chat_user_assistant", "message": "hello"},
        )

    assert response.status_code == 200
    assert response.json() == {"reply": "ok"}
    agent.handle_request.assert_awaited_once_with(
        {"action": "chat_user_assistant", "message": "hello"}
    )
