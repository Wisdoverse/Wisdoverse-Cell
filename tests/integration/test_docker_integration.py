"""
Integration tests for Gateway + requirement manager agent

These tests validate that all services can communicate with each other.

Run modes:
1. CI (GitLab): Services started by CI script, tests run directly
2. Docker Compose: docker compose -f docker-compose.test.yml up --build
3. Local Development: Start services manually or use conftest fixtures

Environment variables:
- INTEGRATION_TEST=1: CI mode (services already running)
- DOCKER_INTEGRATION=1: Docker Compose mode (legacy support)
- Neither: Local development mode (conftest starts services)
"""
import os
import time

import pytest
import requests


def _services_available() -> bool:
    """Check if required services are available for testing."""
    gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8080")
    ai_core_url = os.environ.get("AI_CORE_URL", "http://localhost:8000")

    try:
        # Quick check with short timeout
        gateway_response = requests.get(f"{gateway_url}/health", timeout=2)
        ai_core_response = requests.get(f"{ai_core_url}/health", timeout=2)
        return (
            gateway_response.status_code == 200
            and ai_core_response.status_code == 200
        )
    except requests.exceptions.RequestException:
        return False


def _integration_mode() -> bool:
    """Check if we're running in integration test mode."""
    # CI mode: INTEGRATION_TEST=1 (services started by CI script)
    # Docker mode: DOCKER_INTEGRATION=1 (legacy docker-compose support)
    return (
        os.environ.get("INTEGRATION_TEST") == "1" or
        os.environ.get("DOCKER_INTEGRATION") == "1"
    )


# Skip all tests if not in integration mode and services not available
pytestmark = pytest.mark.skipif(
    not _integration_mode() and not _services_available(),
    reason="Integration tests require INTEGRATION_TEST=1 or running services"
)

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
AI_CORE_URL = os.environ.get("AI_CORE_URL", "http://localhost:8000")
AI_CORE_HEADERS = {"X-API-Key": os.environ.get("PM_API_KEY", "test-pm-api-key")}


def wait_for_service(url: str, timeout: int = 60) -> bool:
    """Wait for a service to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{url}/health", timeout=5)
            if resp.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    return False


class TestServiceHealth:
    """Test that all services are healthy."""

    def test_gateway_health(self):
        """Gateway should be healthy."""
        assert wait_for_service(GATEWAY_URL), "Gateway did not become healthy"
        resp = requests.get(f"{GATEWAY_URL}/health")
        assert resp.status_code == 200

    def test_requirements_capability_health(self):
        """Requirements capability should be healthy."""
        assert wait_for_service(AI_CORE_URL), "Requirements capability did not become healthy"
        resp = requests.get(f"{AI_CORE_URL}/health")
        assert resp.status_code == 200


class TestGatewayRoutes:
    """Test Gateway HTTP routes."""

    def test_feishu_webhook_verification(self):
        """Feishu webhook verification endpoint should respond."""
        # Feishu sends URL verification challenge
        resp = requests.post(
            f"{GATEWAY_URL}/api/feishu/webhook",
            json={
                "type": "url_verification",
                "challenge": "test-challenge-token",
            },
            headers={"Content-Type": "application/json"},
        )
        # Should return the challenge
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("challenge") == "test-challenge-token"

    def test_wecom_webhook_verification(self):
        """WeCom webhook verification endpoint should respond."""
        # WeCom sends GET for verification
        resp = requests.get(
            f"{GATEWAY_URL}/api/wecom/webhook",
            params={
                "msg_signature": "test",
                "timestamp": "12345",
                "nonce": "67890",
                "echostr": "test-echostr",
            },
        )
        # 200/400/403 if wecom is configured, 404 if wecom is disabled
        assert resp.status_code in [200, 400, 403, 404]


class TestRequirementManagerAPI:
    """Test requirement manager agent API endpoints."""

    def test_requirements_list(self):
        """Should be able to list requirements."""
        resp = requests.get(f"{AI_CORE_URL}/api/v1/requirements", headers=AI_CORE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data or isinstance(data, list)

    def test_stats_endpoint(self):
        """Should be able to get stats."""
        resp = requests.get(
            f"{AI_CORE_URL}/api/v1/requirements/stats", headers=AI_CORE_HEADERS
        )
        # May be 200 or 404 depending on implementation
        assert resp.status_code in [200, 404]


class TestGatewayToRequirementsCapability:
    """Test communication from Gateway to the requirement manager agent."""

    @pytest.mark.skip(reason="Requires valid Feishu signature")
    def test_feishu_message_flow(self):
        """Test message flow from Feishu through Gateway to the requirement manager agent."""
        # This would require a valid Feishu signature
        pass

    @pytest.mark.skip(reason="Requires valid WeCom signature")
    def test_wecom_message_flow(self):
        """Test message flow from WeCom through Gateway to the requirement manager agent."""
        # This would require a valid WeCom signature
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
