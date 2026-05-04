"""
Integration Tests - SyncAgent API

Tests sync_agent HTTP endpoints with httpx.AsyncClient.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_agent():
    """Mock SyncAgent instance."""
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
    """Create a test app without starting lifespan."""
    with patch("shared.capabilities.sync.api.sync.get_agent", return_value=mock_agent), \
         patch("shared.capabilities.sync.app.main._raw_agent", mock_agent), \
         patch("shared.capabilities.sync.app.main.settings") as mock_settings:
        mock_settings.debug = True
        mock_settings.cors_origins_list = ["*"]
        mock_settings.cors_allow_credentials = False
        mock_settings.cors_allowed_methods = "GET,POST"
        mock_settings.cors_allowed_headers = "*"
        mock_settings.cors_max_age = 600
        mock_settings.app_env = "test"

        from fastapi import FastAPI

        from shared.capabilities.sync.api.sync import router as sync_router

        app = FastAPI()
        app.include_router(sync_router)

        @app.get("/health")
        async def health():
            return {"status": "alive", "agent": mock_agent.agent_id}

        yield app


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """GET /health should return alive."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["agent"] == "sync-agent-test"


@pytest.mark.asyncio
async def test_trigger_sync(test_app, mock_agent):
    """POST /api/v1/sync/trigger should trigger sync."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/sync/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["total_processed"] == 5
    mock_agent.trigger_sync.assert_called_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_trigger_openproject_sync(test_app, mock_agent):
    """POST /api/v1/sync/openproject/trigger triggers only OpenProject sync."""
    mock_agent.trigger_openproject_sync = AsyncMock(return_value={
        "status": "success",
        "processed": 2,
        "errors": [],
    })

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/sync/openproject/trigger")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_processed"] == 2
    mock_agent.trigger_openproject_sync.assert_called_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_trigger_feishu_bitable_sync(test_app, mock_agent):
    """POST /api/v1/sync/feishu-bitable/trigger triggers only Bitable sync."""
    mock_agent.trigger_feishu_bitable_sync = AsyncMock(return_value={
        "status": "success",
        "processed": 3,
        "errors": [],
    })

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/sync/feishu-bitable/trigger")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_processed"] == 3
    mock_agent.trigger_feishu_bitable_sync.assert_called_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_sync_status(test_app, mock_agent):
    """GET /api/v1/sync/status should return status."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/sync/status")
    assert resp.status_code == 200
    mock_agent.handle_request.assert_called_once_with({"action": "status"})


@pytest.mark.asyncio
async def test_list_mappings(test_app):
    """GET /api/v1/sync/mappings should return the mapping list."""
    with patch("shared.capabilities.sync.api.sync.get_db") as mock_get_db, \
        patch("shared.capabilities.sync.api.sync.SyncMappingRepository") as repo_cls:
        async def _override():
            yield MagicMock()

        mock_get_db.return_value = _override()
        repo = repo_cls.return_value
        repo.list_all = AsyncMock(return_value=[])

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sync/mappings")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {"total": 0, "items": []}
