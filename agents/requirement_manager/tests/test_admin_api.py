"""
Admin API Tests
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


class TestLLMUsageAPI:
    """测试 LLM 使用量 API"""

    @pytest.mark.asyncio
    async def test_get_llm_usage_default_date(self):
        """测试获取今日 LLM 使用量"""
        from agents.requirement_manager.app.main import app

        mock_summary = {
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "total_calls": 10,
            "success_calls": 9,
            "failed_calls": 1,
            "total_input_tokens": 10000,
            "total_output_tokens": 5000,
            "total_cost_usd": 0.105,
            "avg_latency_ms": 1200,
            "by_agent": {
                "requirement-manager": {
                    "calls": 10,
                    "cost_usd": 0.105,
                    "input_tokens": 10000,
                    "output_tokens": 5000
                }
            },
            "by_task_type": {
                "extraction": {"calls": 6, "cost_usd": 0.063},
                "generation": {"calls": 4, "cost_usd": 0.042}
            }
        }

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent, \
             patch("agents.requirement_manager.api.admin.LLMUsageRepository") as MockRepo:

            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.get_daily_summary = AsyncMock(return_value=mock_summary)
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/llm-usage")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 10
        assert data["success_calls"] == 9
        assert data["failed_calls"] == 1
        assert "by_agent" in data
        assert "by_task_type" in data

    @pytest.mark.asyncio
    async def test_get_llm_usage_specific_date(self):
        """测试获取指定日期的 LLM 使用量"""
        from agents.requirement_manager.app.main import app

        mock_summary = {
            "date": "2026-01-15",
            "total_calls": 5,
            "success_calls": 5,
            "failed_calls": 0,
            "total_input_tokens": 5000,
            "total_output_tokens": 2500,
            "total_cost_usd": 0.0525,
            "avg_latency_ms": 1000,
            "by_agent": {},
            "by_task_type": {}
        }

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent, \
             patch("agents.requirement_manager.api.admin.LLMUsageRepository") as MockRepo:

            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.get_daily_summary = AsyncMock(return_value=mock_summary)
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/llm-usage?date=2026-01-15")

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2026-01-15"
        assert data["total_calls"] == 5

    @pytest.mark.asyncio
    async def test_get_llm_usage_filtered_by_agent(self):
        """测试按 Agent 过滤的 LLM 使用量"""
        from agents.requirement_manager.app.main import app

        mock_summary = {
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "total_calls": 3,
            "success_calls": 3,
            "failed_calls": 0,
            "total_input_tokens": 3000,
            "total_output_tokens": 1500,
            "total_cost_usd": 0.0315,
            "avg_latency_ms": 1100,
            "by_agent": {
                "target-agent": {
                    "calls": 3,
                    "cost_usd": 0.0315,
                    "input_tokens": 3000,
                    "output_tokens": 1500
                }
            },
            "by_task_type": {}
        }

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent, \
             patch("agents.requirement_manager.api.admin.LLMUsageRepository") as MockRepo:

            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.get_daily_summary = AsyncMock(return_value=mock_summary)
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/llm-usage?agent_id=target-agent")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 3
        assert "target-agent" in data["by_agent"]


class TestCircuitBreakerAPI:
    """测试断路器 API"""

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(self):
        """测试获取断路器状态"""
        from agents.requirement_manager.app.main import app

        mock_stats = {
            "state": "closed",
            "failures": 0,
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "last_failure_time": None
        }

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent, \
             patch("agents.requirement_manager.api.admin.llm_gateway") as mock_gateway:

            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()
            mock_gateway.get_circuit_breaker_stats.return_value = mock_stats

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/circuit-breaker")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "closed"
        assert data["failures"] == 0
        assert data["failure_threshold"] == 5

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status_open(self):
        """测试断路器打开状态"""
        from agents.requirement_manager.app.main import app

        mock_stats = {
            "state": "open",
            "failures": 5,
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "last_failure_time": "2026-01-22T10:30:00+00:00"
        }

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent, \
             patch("agents.requirement_manager.api.admin.llm_gateway") as mock_gateway:

            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()
            mock_gateway.get_circuit_breaker_stats.return_value = mock_stats

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/circuit-breaker")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "open"
        assert data["failures"] == 5
        assert data["last_failure_time"] is not None

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self):
        """测试重置断路器"""
        from agents.requirement_manager.app.main import app

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent, \
             patch("agents.requirement_manager.api.admin.llm_gateway") as mock_gateway:

            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()
            mock_gateway.reset_circuit_breaker = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post("/api/v1/admin/circuit-breaker/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Circuit breaker reset successfully"
        assert data["state"] == "closed"
        mock_gateway.reset_circuit_breaker.assert_called_once()
