"""
Integration Tests - ChatAgent API

FastAPI endpoint integration tests for health, readiness, and webhook routing.
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_agent():
    """Mock ChatAgent for app-level tests"""
    agent = MagicMock()
    agent.agent_id = "chat-agent"
    agent.startup = AsyncMock()
    agent.shutdown = AsyncMock()
    agent.health_check = AsyncMock(return_value={"database": True, "chat_service": True})
    agent._db_manager = MagicMock()

    # mock db health check
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    agent._db_manager.session = MagicMock(return_value=session_cm)

    return agent


@pytest.fixture
def test_app(mock_agent):
    """Create test FastAPI app with mocked webhook agent lookup."""
    with (
        patch("services.gateways.user_interaction.api.webhook.get_agent", return_value=mock_agent),
        patch("services.gateways.user_interaction.api.webhook.settings") as mock_settings,
    ):
        mock_settings.feishu_verify_signature = False
        from services.gateways.user_interaction.app.main import app
        yield app


@pytest.mark.asyncio
async def test_health_endpoint(test_app, mock_agent):
    """GET /health returns liveness."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["agent"] == "chat-agent"


@pytest.mark.asyncio
async def test_readiness_endpoint(test_app, mock_agent):
    """GET /health/ready returns runtime readiness state."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")

    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert data["agent"] == "chat-agent"


@pytest.mark.asyncio
async def test_webhook_challenge(test_app, mock_agent):
    """POST /webhook/feishu echoes challenge values."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/feishu",
            json={"challenge": "test_challenge_token"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["challenge"] == "test_challenge_token"


@pytest.mark.asyncio
async def test_daily_progress_route_delegates_to_query_service():
    """GET /api/daily-progress should delegate read logic to the query use case."""
    from fastapi import FastAPI

    from services.gateways.user_interaction.api.daily_progress import (
        router as daily_progress_router,
    )
    from services.gateways.user_interaction.api.dependencies import (
        get_daily_progress_query_service,
    )
    query_service = MagicMock()
    expected = {
        "entries": [
            {
                "id": 1,
                "user_id": "u_1",
                "user_name": "Alice",
                "date": "2026-05-17",
                "task_record_id": "rec_1",
                "task_title": "Ship backend boundary",
                "status": "done",
                "note": "completed",
                "raw_reply": "done",
            }
        ],
        "total": 1,
    }
    query_service.list_progress_response = AsyncMock(
        return_value=expected,
    )
    app = FastAPI()
    app.include_router(daily_progress_router)
    app.dependency_overrides[get_daily_progress_query_service] = lambda: query_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/daily-progress",
            params={"target_date": "2026-05-17", "user_id": "u_1", "days": 2},
    )

    assert resp.status_code == 200
    assert resp.json() == expected
    query_service.list_progress_response.assert_awaited_once_with(
        target_date=date(2026, 5, 17),
        user_id="u_1",
        days=2,
    )


@pytest.mark.asyncio
async def test_webhook_non_message_event(test_app, mock_agent):
    """POST /webhook/feishu returns code=0 for non-message events."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/feishu",
            json={
                "header": {"event_type": "im.chat.member.bot.added_v1"},
                "event": {},
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
