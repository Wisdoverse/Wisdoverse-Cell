"""Authentication coverage for channel-gateway outbound API surfaces."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shared.messaging.outbound.api.admin import router as admin_router
from shared.messaging.outbound.api.health import router as health_router


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(health_router)
    test_app.include_router(admin_router)
    return test_app


@pytest.mark.asyncio
async def test_channel_gateway_admin_requires_internal_key(app: FastAPI) -> None:
    with patch("shared.middleware.internal_auth.settings") as mock_settings:
        mock_settings.internal_service_key = "secret-key"
        mock_settings.app_env = "test"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            missing = await client.get("/api/admin/adapters")
            allowed = await client.get(
                "/api/admin/adapters",
                headers={"X-Internal-Key": "secret-key"},
            )

    assert missing.status_code == 401
    assert allowed.status_code == 200
    assert "adapters" in allowed.json()


@pytest.mark.asyncio
async def test_channel_gateway_adapter_health_requires_internal_key(app: FastAPI) -> None:
    with patch("shared.middleware.internal_auth.settings") as mock_settings:
        mock_settings.internal_service_key = "secret-key"
        mock_settings.app_env = "test"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            public_health = await client.get("/health")
            missing_detail = await client.get("/health/adapters")
            allowed_detail = await client.get(
                "/health/adapters",
                headers={"X-Internal-Key": "secret-key"},
            )

    assert public_health.status_code == 200
    assert missing_detail.status_code == 401
    assert allowed_detail.status_code == 200
    assert "adapters" in allowed_detail.json()
