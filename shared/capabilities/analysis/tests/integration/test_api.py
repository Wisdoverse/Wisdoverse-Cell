"""
Integration Tests - AnalysisModule API

Tests analysis capability HTTP endpoints with httpx.AsyncClient.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from shared.api import ApiErrorCode


@pytest.fixture
def mock_agent():
    """Create a mock AnalysisModule instance."""
    agent = MagicMock()
    agent.agent_id = "analysis-module-test"
    agent._db_manager = None
    agent._event_bus = MagicMock()
    agent.handle_request = AsyncMock()
    return agent


@pytest.fixture
def test_app(mock_agent):
    """Create a test app without starting lifespan."""
    with patch("shared.capabilities.analysis.api.analysis.get_agent", return_value=mock_agent), \
         patch("shared.capabilities.analysis.app.main._raw_agent", mock_agent):

        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from shared.capabilities.analysis.api.analysis import router as analysis_router

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
    """GET /health should return alive."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness_endpoint(test_app, mock_agent):
    """GET /health/ready should return ready status."""
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
    """Unavailable dependencies should return degraded status."""
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
    """POST /api/v1/analysis/daily should trigger daily report generation."""
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
    """POST /api/v1/analysis/weekly should trigger weekly report generation."""
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
    """GET /api/v1/analysis/risks should return the risk list."""
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
    """Daily report generation failure should return 500."""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/analysis/daily")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Daily report generation failed. Please retry later."
    assert resp.headers["x-error-code"] == ApiErrorCode.ANALYSIS_DAILY_REPORT_FAILED.value


@pytest.mark.asyncio
async def test_generate_weekly_error(test_app, mock_agent):
    """Weekly report generation failure should expose a stable error code."""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/analysis/weekly")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Weekly report generation failed. Please retry later."
    assert resp.headers["x-error-code"] == ApiErrorCode.ANALYSIS_WEEKLY_REPORT_FAILED.value


@pytest.mark.asyncio
async def test_check_risks_error(test_app, mock_agent):
    """Risk check failure should expose a stable error code."""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/analysis/risks")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Risk check failed. Please retry later."
    assert resp.headers["x-error-code"] == ApiErrorCode.ANALYSIS_RISK_CHECK_FAILED.value


@pytest.mark.asyncio
async def test_check_risks_empty(test_app, mock_agent):
    """No risks should return an empty list."""
    mock_agent.handle_request.return_value = {"risks": []}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/analysis/risks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["risks"] == []
