"""Integration Test - QA Agent API"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from agents.qa_agent.app.main import app
from agents.qa_agent.models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceSummary,
    QACheckAggregate,
    QARunStats,
)
from shared.config import settings


@pytest.fixture
def api_client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-Internal-Key": settings.internal_service_key or "test-key"}


@pytest.mark.asyncio
async def test_health_check(api_client):
    """测试健康检查 (通常由 create_agent_app 自动添加)"""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_trigger_run_success(auth_headers):
    """测试手动触发验收成功"""
    mock_result = MagicMock(spec=AcceptanceExecutionResult)
    mock_result.summary = AcceptanceSummary(
        l0_gate="PASS",
        l1_check="PASS",
        l2_report="INFO",
        total_checks=10,
        l0_failures=0,
        l1_warnings=0,
    )
    mock_result.duration_seconds = 1.5
    mock_result.run_id = "run_123"
    mock_result.notification_summary = {"feishu": {"sent": True}}

    mock_agent = AsyncMock()
    mock_agent.run_acceptance.return_value = mock_result

    with patch("agents.qa_agent.api.qa.get_agent", return_value=mock_agent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/qa/run",
                json={"agent_name": "pjm_agent", "requested_by": "tester"},
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "run_123"
    assert data["status"] == "passed"
    assert data["summary"]["l0_gate"] == "PASS"


@pytest.mark.asyncio
async def test_list_runs(auth_headers):
    """测试查询运行列表"""
    mock_runs = [
        {
            "id": "run_1",
            "agent_name": "pjm_agent",
            "trigger": "manual",
            "l0_status": "PASS",
            "l1_status": "PASS",
            "total_checks": 5,
            "duration_seconds": 0.8,
            "created_at": datetime.now(UTC).isoformat(),
        }
    ]

    mock_agent = AsyncMock()
    mock_agent.list_runs.return_value = mock_runs

    with patch("agents.qa_agent.api.qa.get_agent", return_value=mock_agent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/qa/runs", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["run_id"] == "run_1"


@pytest.mark.asyncio
async def test_get_run_detail_not_found(auth_headers):
    """测试查询不存在的记录"""
    mock_agent = AsyncMock()
    mock_agent.get_run.return_value = None

    with patch("agents.qa_agent.api.qa.get_agent", return_value=mock_agent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/qa/runs/missing", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_stats(auth_headers):
    """测试查询统计数据"""
    mock_stats = QARunStats(
        agent_name="pjm_agent",
        days=7,
        total_runs=10,
        pass_runs=8,
        warn_runs=1,
        failed_runs=1,
        l0_fail_rate=0.1,
        avg_duration_seconds=1.2,
        top_l0_failures=[QACheckAggregate(check="security", count=1)],
        top_l1_warnings=[],
    )

    mock_agent = AsyncMock()
    mock_agent.get_stats.return_value = mock_stats

    with patch("agents.qa_agent.api.qa.get_agent", return_value=mock_agent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/qa/stats?agent_name=pjm_agent&days=7",
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] == 10
    assert data["l0_fail_rate"] == 0.1
    assert data["top_l0_failures"][0]["check"] == "security"


@pytest.mark.asyncio
async def test_unauthorized(api_client):
    """测试未授权访问"""
    # 强制设置一个 key 以确保验证逻辑生效
    with patch("shared.config.settings.internal_service_key", "secret-key"):
        response = api_client.get("/api/v1/qa/runs")
        assert response.status_code == 401
