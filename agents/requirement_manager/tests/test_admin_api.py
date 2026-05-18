"""
Admin API Tests
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


class TestLLMUsageAPI:
    """LLM usage API tests."""

    @pytest.mark.asyncio
    async def test_get_llm_usage_default_date(self):
        """Get LLM usage for the current date."""
        from agents.requirement_manager.api.dependencies import get_llm_usage_query_service
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

        query_service = MagicMock()
        query_service.get_daily_summary = AsyncMock(return_value=mock_summary)
        app.dependency_overrides[get_llm_usage_query_service] = lambda: query_service
        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:

                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/llm-usage")
        finally:
            app.dependency_overrides.pop(get_llm_usage_query_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 10
        assert data["success_calls"] == 9
        assert data["failed_calls"] == 1
        assert "by_agent" in data
        assert "by_task_type" in data
        query_service.get_daily_summary.assert_awaited_once_with(
            date=None,
            agent_id=None,
        )

    @pytest.mark.asyncio
    async def test_get_llm_usage_specific_date(self):
        """Get LLM usage for a specific date."""
        from agents.requirement_manager.api.dependencies import get_llm_usage_query_service
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

        query_service = MagicMock()
        query_service.get_daily_summary = AsyncMock(return_value=mock_summary)
        app.dependency_overrides[get_llm_usage_query_service] = lambda: query_service
        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:

                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/llm-usage?date=2026-01-15")
        finally:
            app.dependency_overrides.pop(get_llm_usage_query_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2026-01-15"
        assert data["total_calls"] == 5
        query_service.get_daily_summary.assert_awaited_once_with(
            date="2026-01-15",
            agent_id=None,
        )

    @pytest.mark.asyncio
    async def test_get_llm_usage_filtered_by_agent(self):
        """Get LLM usage filtered by Agent."""
        from agents.requirement_manager.api.dependencies import get_llm_usage_query_service
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

        query_service = MagicMock()
        query_service.get_daily_summary = AsyncMock(return_value=mock_summary)
        app.dependency_overrides[get_llm_usage_query_service] = lambda: query_service
        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:

                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/llm-usage?agent_id=target-agent")
        finally:
            app.dependency_overrides.pop(get_llm_usage_query_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 3
        assert "target-agent" in data["by_agent"]
        query_service.get_daily_summary.assert_awaited_once_with(
            date=None,
            agent_id="target-agent",
        )


class TestCircuitBreakerAPI:
    """Circuit breaker API tests."""

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(self):
        """Get circuit breaker status."""
        from agents.requirement_manager.api.dependencies import (
            get_circuit_breaker_admin_use_case,
        )
        from agents.requirement_manager.app.main import app
        from agents.requirement_manager.core.admin_circuit_breaker import (
            CircuitBreakerStatus,
        )

        circuit_breaker = MagicMock()
        circuit_breaker.get_status.return_value = CircuitBreakerStatus(
            state="closed",
            failures=0,
            failure_threshold=5,
            recovery_timeout=60,
            last_failure_time=None,
        )
        app.dependency_overrides[get_circuit_breaker_admin_use_case] = (
            lambda: circuit_breaker
        )

        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:

                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/circuit-breaker")
        finally:
            app.dependency_overrides.pop(get_circuit_breaker_admin_use_case, None)

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "closed"
        assert data["failures"] == 0
        assert data["failure_threshold"] == 5
        circuit_breaker.get_status.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status_open(self):
        """Get open circuit breaker status."""
        from agents.requirement_manager.api.dependencies import (
            get_circuit_breaker_admin_use_case,
        )
        from agents.requirement_manager.app.main import app
        from agents.requirement_manager.core.admin_circuit_breaker import (
            CircuitBreakerStatus,
        )

        circuit_breaker = MagicMock()
        circuit_breaker.get_status.return_value = CircuitBreakerStatus(
            state="open",
            failures=5,
            failure_threshold=5,
            recovery_timeout=60,
            last_failure_time="2026-01-22T10:30:00+00:00",
        )
        app.dependency_overrides[get_circuit_breaker_admin_use_case] = (
            lambda: circuit_breaker
        )

        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:

                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/circuit-breaker")
        finally:
            app.dependency_overrides.pop(get_circuit_breaker_admin_use_case, None)

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "open"
        assert data["failures"] == 5
        assert data["last_failure_time"] is not None
        circuit_breaker.get_status.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self):
        """Reset the circuit breaker."""
        from agents.requirement_manager.api.dependencies import (
            get_circuit_breaker_admin_use_case,
        )
        from agents.requirement_manager.app.main import app

        circuit_breaker = MagicMock()
        circuit_breaker.reset = MagicMock()
        app.dependency_overrides[get_circuit_breaker_admin_use_case] = (
            lambda: circuit_breaker
        )

        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:

                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.post("/api/v1/admin/circuit-breaker/reset")
        finally:
            app.dependency_overrides.pop(get_circuit_breaker_admin_use_case, None)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Circuit breaker reset successfully"
        assert data["state"] == "closed"
        circuit_breaker.reset.assert_called_once_with()
