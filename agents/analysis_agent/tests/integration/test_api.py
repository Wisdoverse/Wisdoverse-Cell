"""
Integration Tests - AnalysisAgent API

使用 httpx.AsyncClient 测试 analysis_agent 的 HTTP 端点。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_agent():
    """模拟 AnalysisAgent 实例"""
    agent = MagicMock()
    agent.agent_id = "analysis-agent-test"
    agent._db_manager = None
    agent._event_bus = MagicMock()
    agent.handle_request = AsyncMock()
    return agent


@pytest.fixture
def test_app(mock_agent):
    """创建不启动 lifespan 的测试 app"""
    with patch("agents.analysis_agent.api.analysis.get_agent", return_value=mock_agent), \
         patch("agents.analysis_agent.app.main.agent", mock_agent):

        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from agents.analysis_agent.api.analysis import router as analysis_router

        app = FastAPI()
        app.include_router(analysis_router)

        @app.get("/health")
        async def health():
            return {"status": "alive", "agent": mock_agent.agent_id}

        @app.get("/health/ready")
        async def readiness():
            checks = {"database": False, "event_bus": False}
            try:
                if mock_agent._db_manager:
                    checks["database"] = True
            except Exception:
                pass
            checks["event_bus"] = mock_agent._event_bus is not None
            all_ok = all(checks.values())
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


@pytest.mark.asyncio
async def test_readiness_endpoint(test_app, mock_agent):
    """GET /health/ready 应返回就绪状态"""
    mock_agent._db_manager = MagicMock()
    mock_agent._event_bus = MagicMock()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["event_bus"] is True


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
async def test_generate_daily(test_app, mock_agent):
    """POST /api/v1/analysis/daily 应触发日报生成"""
    mock_agent.handle_request.return_value = {
        "status": "ok",
        "content": "日报内容",
        "summary": "共 5 个任务",
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/analysis/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "日报内容"
    assert data["summary"] == "共 5 个任务"
    mock_agent.handle_request.assert_called_once_with({"action": "daily_report"})


@pytest.mark.asyncio
async def test_generate_weekly(test_app, mock_agent):
    """POST /api/v1/analysis/weekly 应触发周报生成"""
    mock_agent.handle_request.return_value = {
        "status": "ok",
        "content": "周报内容",
        "summary": "本周完成 10 个任务",
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/analysis/weekly")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "周报内容"
    mock_agent.handle_request.assert_called_once_with({"action": "weekly_report"})


@pytest.mark.asyncio
async def test_check_risks(test_app, mock_agent):
    """GET /api/v1/analysis/risks 应返回风险列表"""
    mock_agent.handle_request.return_value = {
        "risks": [
            {"feature": "#100", "risk_level": "critical", "description": "阻塞", "affected_tasks": ["A"]},
        ]
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/analysis/risks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["risks"]) == 1
    mock_agent.handle_request.assert_called_once_with({"action": "check_milestones"})


@pytest.mark.asyncio
async def test_generate_daily_error(test_app, mock_agent):
    """日报生成失败时应返回 500"""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/analysis/daily")
    assert resp.status_code == 500
    assert "日报生成失败" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_check_risks_empty(test_app, mock_agent):
    """无风险时应返回空列表"""
    mock_agent.handle_request.return_value = {"risks": []}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/analysis/risks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["risks"] == []
