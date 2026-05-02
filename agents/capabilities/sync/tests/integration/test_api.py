"""
Integration Tests - SyncAgent API

使用 httpx.AsyncClient 测试 sync_agent 的 HTTP 端点。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_agent():
    """模拟 SyncAgent 实例"""
    agent = MagicMock()
    agent.agent_id = "sync-agent-test"
    agent.trigger_sync = AsyncMock(return_value={
        "status": "completed",
        "total_processed": 5,
        "errors": [],
    })
    agent.handle_request = AsyncMock(return_value={
        "status": "ok",
        "agent_id": "sync-agent-test",
    })
    agent._db_manager = None
    return agent


@pytest.fixture
def test_app(mock_agent):
    """创建不启动 lifespan 的测试 app"""
    with patch("agents.capabilities.sync.api.sync.get_agent", return_value=mock_agent), \
         patch("agents.capabilities.sync.app.main.agent", mock_agent), \
         patch("agents.capabilities.sync.app.main.settings") as mock_settings:
        mock_settings.debug = True
        mock_settings.cors_origins_list = ["*"]
        mock_settings.cors_allow_credentials = False
        mock_settings.cors_allowed_methods = "GET,POST"
        mock_settings.cors_allowed_headers = "*"
        mock_settings.cors_max_age = 600
        mock_settings.app_env = "test"

        from fastapi import FastAPI

        from agents.capabilities.sync.api.sync import router as sync_router

        app = FastAPI()
        app.include_router(sync_router)

        @app.get("/health")
        async def health():
            return {"status": "alive", "agent": mock_agent.agent_id}

        yield app


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """GET /health 应返回 alive"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["agent"] == "sync-agent-test"


@pytest.mark.asyncio
async def test_trigger_sync(test_app, mock_agent):
    """POST /api/v1/sync/trigger 应触发同步"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/sync/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["total_processed"] == 5
    mock_agent.trigger_sync.assert_called_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_sync_status(test_app, mock_agent):
    """GET /api/v1/sync/status 应返回状态"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/sync/status")
    assert resp.status_code == 200
    mock_agent.handle_request.assert_called_once_with({"action": "status"})


@pytest.mark.asyncio
async def test_list_mappings(test_app, db_session):
    """GET /api/v1/sync/mappings 应返回映射列表"""
    with patch("agents.capabilities.sync.api.sync.get_db") as mock_get_db:
        async def _override():
            yield db_session

        mock_get_db.return_value = _override()

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sync/mappings")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
