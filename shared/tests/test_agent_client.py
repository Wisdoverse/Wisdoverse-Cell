"""Tests for inter-agent HTTP client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from shared.infra.agent_client import AgentClient, PMAgentClient


@pytest.fixture
def pm_client():
    return PMAgentClient(base_url="http://test-pm:8012")


class TestAgentClient:
    @pytest.mark.asyncio
    async def test_post_sends_internal_key_and_trace_id(self):
        mock_resp = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("POST", "http://test"),
        )
        with (
            patch("shared.infra.agent_client.settings") as mock_settings,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post,
        ):
            mock_settings.internal_service_key = "secret-key"
            client = AgentClient("http://test-pm:8012")

            result = await client.post(
                "/agent/request",
                json={"action": "wakeup"},
                trace_id="trace-http-1",
            )

        assert result == {"ok": True}
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Internal-Key"] == "secret-key"
        assert headers["X-Trace-ID"] == "trace-http-1"

    @pytest.mark.asyncio
    async def test_get_sends_trace_id_without_internal_key_when_unconfigured(self):
        mock_resp = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("GET", "http://test"),
        )
        with (
            patch("shared.infra.agent_client.settings") as mock_settings,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp) as mock_get,
        ):
            mock_settings.internal_service_key = ""
            client = AgentClient("http://test-pm:8012")

            result = await client.get("/health/ready", trace_id="trace-http-2")

        assert result == {"ok": True}
        headers = mock_get.call_args.kwargs["headers"]
        assert headers == {"X-Trace-ID": "trace-http-2"}


class TestPMAgentClient:
    @pytest.mark.asyncio
    async def test_approve_success(self, pm_client):
        mock_resp = httpx.Response(
            200,
            json={"status": "approved", "wp_id": 42, "subject": "Feature X", "story_count": 3, "task_count": 8},
            request=httpx.Request("POST", "http://test"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await pm_client.approve_decomposition(wp_id=42, operator="user1")
        assert result["status"] == "approved"
        assert result["wp_id"] == 42

    @pytest.mark.asyncio
    async def test_approve_not_found_returns_none(self, pm_client):
        mock_resp = httpx.Response(
            404,
            json={"detail": "Not found"},
            request=httpx.Request("POST", "http://test"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await pm_client.approve_decomposition(wp_id=999, operator="user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_reject_success(self, pm_client):
        mock_resp = httpx.Response(
            200,
            json={"status": "rejected", "wp_id": 42, "subject": "Feature X"},
            request=httpx.Request("POST", "http://test"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await pm_client.reject_decomposition(wp_id=42, operator="user1", reason="Not good")
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_not_found_returns_none(self, pm_client):
        mock_resp = httpx.Response(
            404,
            json={"detail": "Not found"},
            request=httpx.Request("POST", "http://test"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await pm_client.reject_decomposition(wp_id=999, operator="user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_decomposition_success(self, pm_client):
        mock_resp = httpx.Response(
            200,
            json={"wp_id": 42, "status": "pending", "decompose_result": {}},
            request=httpx.Request("GET", "http://test"),
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await pm_client.get_decomposition(wp_id=42)
        assert result["wp_id"] == 42

    @pytest.mark.asyncio
    async def test_get_decomposition_not_found(self, pm_client):
        mock_resp = httpx.Response(
            404,
            json={"detail": "Not found"},
            request=httpx.Request("GET", "http://test"),
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await pm_client.get_decomposition(wp_id=999)
        assert result is None

    @pytest.mark.asyncio
    async def test_server_error_raises(self, pm_client):
        mock_resp = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("POST", "http://test"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                await pm_client.approve_decomposition(wp_id=42, operator="user1")

    @pytest.mark.asyncio
    async def test_approve_decomposition_passes_trace_id(self, pm_client):
        pm_client._client.post = AsyncMock(return_value={"status": "approved"})

        result = await pm_client.approve_decomposition(
            wp_id=42,
            operator="user1",
            trace_id="trace-pm-approve",
        )

        assert result == {"status": "approved"}
        pm_client._client.post.assert_awaited_once_with(
            "/api/v1/pm/decompose/42/approve",
            json={"operator": "user1"},
            trace_id="trace-pm-approve",
        )
