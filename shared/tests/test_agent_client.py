"""Tests for inter-agent HTTP client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from shared.infra.agent_client import (
    AgentClient,
    AgentClientErrorCategory,
    PMAgentClient,
    classify_agent_client_error,
)


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

    @pytest.mark.parametrize(
        ("status_code", "category"),
        [
            (401, AgentClientErrorCategory.AUTH),
            (403, AgentClientErrorCategory.AUTH),
            (429, AgentClientErrorCategory.RATE_LIMIT),
            (413, AgentClientErrorCategory.CONTENT_SIZE),
            (414, AgentClientErrorCategory.CONTENT_SIZE),
            (431, AgentClientErrorCategory.CONTENT_SIZE),
            (500, AgentClientErrorCategory.OVERLOADED),
            (502, AgentClientErrorCategory.OVERLOADED),
            (503, AgentClientErrorCategory.OVERLOADED),
            (504, AgentClientErrorCategory.OVERLOADED),
            (529, AgentClientErrorCategory.OVERLOADED),
            (418, AgentClientErrorCategory.OTHER),
        ],
    )
    def test_classify_http_status_errors(self, status_code, category):
        request = httpx.Request("POST", "http://agent.test/agent/request")
        response = httpx.Response(status_code, request=request)
        exc = httpx.HTTPStatusError(
            "request failed",
            request=request,
            response=response,
        )

        assert classify_agent_client_error(exc) == category

    def test_classify_request_errors_as_network(self):
        request = httpx.Request("GET", "http://agent.test/health")
        exc = httpx.ConnectError("connection refused", request=request)

        assert classify_agent_client_error(exc) == AgentClientErrorCategory.NETWORK

    @pytest.mark.asyncio
    async def test_post_logs_classified_failure_without_wrapping_exception(self):
        mock_resp = httpx.Response(
            503,
            text="Service unavailable",
            request=httpx.Request("POST", "http://test"),
        )
        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp),
            patch("shared.infra.agent_client.logger") as mock_logger,
        ):
            client = AgentClient("http://test-pm:8012")

            with pytest.raises(httpx.HTTPStatusError):
                await client.post(
                    "/agent/request",
                    json={"action": "wakeup"},
                    trace_id="trace-classified",
                )

        warning = mock_logger.warning.call_args
        assert warning.args == ("agent_http_request_failed",)
        assert warning.kwargs["method"] == "POST"
        assert warning.kwargs["path"] == "/agent/request"
        assert warning.kwargs["error_category"] == AgentClientErrorCategory.OVERLOADED.value
        assert warning.kwargs["retry_decision"] == "retry_with_backoff"
        assert warning.kwargs["operator_action"] == "check_target_service_health"
        assert warning.kwargs["status_code"] == 503
        assert warning.kwargs["trace_id"] == "trace-classified"

    @pytest.mark.asyncio
    async def test_get_logs_auth_failure_operator_action(self):
        mock_resp = httpx.Response(
            403,
            text="Forbidden",
            request=httpx.Request("GET", "http://test"),
        )
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp),
            patch("shared.infra.agent_client.logger") as mock_logger,
        ):
            client = AgentClient("http://test-pm:8012")

            with pytest.raises(httpx.HTTPStatusError):
                await client.get("/agent/request", trace_id="trace-auth-failure")

        warning = mock_logger.warning.call_args
        assert warning.args == ("agent_http_request_failed",)
        assert warning.kwargs["error_category"] == AgentClientErrorCategory.AUTH.value
        assert warning.kwargs["retry_decision"] == "do_not_retry_until_auth_is_fixed"
        assert (
            warning.kwargs["operator_action"]
            == "check_internal_service_key_and_target_auth_policy"
        )
        assert warning.kwargs["status_code"] == 403
        assert warning.kwargs["trace_id"] == "trace-auth-failure"


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
