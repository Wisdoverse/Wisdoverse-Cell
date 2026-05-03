"""Tests for authenticated DSAR API routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shared.api.dsar_router import create_dsar_router
from shared.schemas.dsar import DSARResult


class _FakeDSARService:
    def __init__(self) -> None:
        self.export_user_data = AsyncMock(return_value={"chat_messages": [{"id": 1}]})
        self.delete_user_data = AsyncMock(
            return_value=DSARResult(
                user_id="user_1",
                action="delete",
                affected_tables={"chat_messages": 1},
                status="completed",
            )
        )


@pytest.mark.asyncio
async def test_dsar_export_requires_internal_key() -> None:
    service = _FakeDSARService()
    app = FastAPI()
    app.include_router(create_dsar_router(service))

    with patch("shared.middleware.internal_auth.settings") as mock_settings:
        mock_settings.internal_service_key = "test-secret"
        mock_settings.app_env = "test"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            missing = await client.post("/api/dsar/export", json={"user_id": "user_1"})
            wrong = await client.post(
                "/api/dsar/export",
                headers={"X-Internal-Key": "wrong"},
                json={"user_id": "user_1"},
            )
            ok = await client.post(
                "/api/dsar/export",
                headers={"X-Internal-Key": "test-secret"},
                json={"user_id": "user_1"},
            )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert ok.status_code == 200
    assert ok.json()["affected_tables"] == {"chat_messages": 1}
    service.export_user_data.assert_awaited_once_with("user_1")


@pytest.mark.asyncio
async def test_dsar_delete_requires_internal_key() -> None:
    service = _FakeDSARService()
    app = FastAPI()
    app.include_router(create_dsar_router(service))

    with patch("shared.middleware.internal_auth.settings") as mock_settings:
        mock_settings.internal_service_key = "test-secret"
        mock_settings.app_env = "test"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            missing = await client.post(
                "/api/dsar/delete?confirm=true",
                json={"user_id": "user_1"},
            )
            ok = await client.post(
                "/api/dsar/delete?confirm=true",
                headers={"X-Internal-Key": "test-secret"},
                json={"user_id": "user_1"},
            )

    assert missing.status_code == 401
    assert ok.status_code == 200
    assert ok.json()["action"] == "delete"
    service.delete_user_data.assert_awaited_once_with("user_1", dry_run=False)
