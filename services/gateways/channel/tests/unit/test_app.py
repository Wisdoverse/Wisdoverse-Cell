"""Tests for the channel gateway shared runtime entry point."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.gateways.channel.app.main import app
from shared.app import AgentRuntime


def test_channel_gateway_app_uses_shared_runtime() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert isinstance(app.state.runtime, AgentRuntime)
    assert app.state.runtime.agent_id == "channel-gateway"
    assert "/agent/request" in paths
    assert "/health/ready/detail" in paths
    assert "/api/admin/adapters" in paths
    assert "/health/adapters" in paths


@pytest.mark.asyncio
async def test_agent_request_requires_internal_key() -> None:
    with patch("shared.middleware.internal_auth.settings") as mock_settings:
        mock_settings.internal_service_key = "secret-key"
        mock_settings.app_env = "test"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            missing = await client.post("/agent/request", json={"action": "describe"})
            allowed = await client.post(
                "/agent/request",
                headers={"X-Internal-Key": "secret-key"},
                json={"action": "describe"},
            )

    assert missing.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["agent_id"] == "channel-gateway"
