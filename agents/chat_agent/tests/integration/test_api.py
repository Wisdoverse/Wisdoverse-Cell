"""
Integration Tests - ChatAgent API

FastAPI 端点集成测试（health、readiness、webhook）。
"""
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
    """Create test FastAPI app with mocked agent"""
    with patch("agents.chat_agent.app.main.agent", mock_agent), \
         patch("agents.chat_agent.api.webhook.get_agent", return_value=mock_agent):
        from agents.chat_agent.app.main import app
        yield app


@pytest.mark.asyncio
async def test_health_endpoint(test_app, mock_agent):
    """GET /health 返回 alive 状态"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["agent"] == "chat-agent"


@pytest.mark.asyncio
async def test_readiness_endpoint(test_app, mock_agent):
    """GET /health/ready 返回就绪检查结果"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")

    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "chat_service" in data["checks"]


@pytest.mark.asyncio
async def test_webhook_challenge(test_app, mock_agent):
    """POST /webhook/feishu 带 challenge 字段时回显 challenge"""
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
async def test_webhook_non_message_event(test_app, mock_agent):
    """POST /webhook/feishu 非消息事件返回 code=0"""
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
