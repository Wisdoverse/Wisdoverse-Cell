from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agents.chat_agent.api.conversation import router


@pytest.mark.asyncio
async def test_get_conversation_history_calls_chat_agent_request_boundary() -> None:
    agent = SimpleNamespace(handle_request=AsyncMock(return_value={"messages": []}))
    app = FastAPI()
    app.state.runtime = SimpleNamespace(agent=agent)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/chat-agent/conversation/u_1")

    assert response.status_code == 200
    assert response.json() == {"messages": []}
    agent.handle_request.assert_awaited_once_with(
        {
            "action": "get_conversation_history",
            "user_id": "u_1",
        }
    )
