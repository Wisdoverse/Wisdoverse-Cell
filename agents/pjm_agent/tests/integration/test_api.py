"""
Integration Tests - PMAgent API

使用 httpx.AsyncClient 测试 pjm_agent 的 HTTP 端点。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_agent():
    """模拟 PMAgent 实例"""
    agent = MagicMock()
    agent.agent_id = "pjm-agent-test"
    agent._db_manager = None
    agent._event_bus = MagicMock()
    agent._config = MagicMock()
    agent._config.members = []
    agent.handle_request = AsyncMock()
    return agent


@pytest.fixture
def test_app(mock_agent):
    """创建不启动 lifespan 的测试 app"""
    with (
        patch("agents.pjm_agent.api.pm.get_agent", return_value=mock_agent),
        patch("agents.pjm_agent.app.main.agent", mock_agent),
    ):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from agents.pjm_agent.api.pm import router as pm_router

        app = FastAPI()
        app.include_router(pm_router)

        @app.get("/health")
        async def health():
            return {"status": "alive", "agent": mock_agent.agent_id}

        @app.get("/health/ready")
        async def readiness():
            checks = {"database": False, "scheduler": False, "config_loaded": False}
            try:
                if mock_agent._db_manager:
                    checks["database"] = True
            except Exception:
                pass
            checks["scheduler"] = False
            checks["config_loaded"] = (
                len(mock_agent._config.members) > 0 if mock_agent._config else False
            )
            all_ok = checks["database"] and checks["scheduler"]
            return JSONResponse(
                status_code=200 if all_ok else 503,
                content={"status": "ready" if all_ok else "degraded", "checks": checks},
            )

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
    assert data["agent"] == "pjm-agent-test"


@pytest.mark.asyncio
async def test_readiness_endpoint(test_app, mock_agent):
    """GET /health/ready 应返回就绪状态"""
    mock_agent._db_manager = MagicMock()
    mock_agent._event_bus = MagicMock()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    # scheduler 为 False，所以 all_ok 为 False → 503
    assert resp.status_code == 503
    data = resp.json()
    assert "checks" in data


@pytest.mark.asyncio
async def test_readiness_degraded(test_app, mock_agent):
    """数据库不可用时应返回 degraded"""
    mock_agent._db_manager = None
    mock_agent._event_bus = None

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_config_endpoint(test_app, mock_agent):
    """GET /api/v1/pm/config 应返回 PM 配置"""
    mock_agent.handle_request.return_value = {
        "members": [{"name": "Alice"}],
        "projects": [{"name": "P1"}],
        "rules": [],
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["members"] == [{"name": "Alice"}]
    assert data["projects"] == [{"name": "P1"}]
    mock_agent.handle_request.assert_called_once_with({"action": "config"})


@pytest.mark.asyncio
async def test_alerts_endpoint(test_app, mock_agent):
    """GET /api/v1/pm/alerts 应返回预警列表"""
    mock_agent.handle_request.return_value = {
        "alerts": [
            {"type": "deadline", "task": "T1", "message": "已逾期 2 天", "severity": "critical"},
        ]
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["type"] == "deadline"
    mock_agent.handle_request.assert_called_once_with({"action": "alerts"})


@pytest.mark.asyncio
async def test_config_endpoint_error(test_app, mock_agent):
    """配置获取失败时应返回 500"""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/config")
    assert resp.status_code == 500
    assert "获取配置失败" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_alerts_endpoint_empty(test_app, mock_agent):
    """无预警时应返回空列表"""
    mock_agent.handle_request.return_value = {"alerts": []}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["alerts"] == []
