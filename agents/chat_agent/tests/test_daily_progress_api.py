from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agents.chat_agent.api.daily_progress import router


@pytest.mark.asyncio
async def test_get_daily_progress_calls_chat_agent_request_boundary() -> None:
    agent = SimpleNamespace(handle_request=AsyncMock(return_value={"entries": [], "total": 0}))
    app = FastAPI()
    app.state.runtime = SimpleNamespace(agent=agent)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/daily-progress",
            params={"target_date": "2026-05-17", "user_id": "u_1", "days": 2},
        )

    assert response.status_code == 200
    assert response.json() == {"entries": [], "total": 0}
    agent.handle_request.assert_awaited_once_with(
        {
            "action": "list_daily_progress",
            "target_date": date(2026, 5, 17),
            "user_id": "u_1",
            "days": 2,
        }
    )
