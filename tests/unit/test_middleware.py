"""Unit tests for shared.middleware.APIKeyMiddleware."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from shared import middleware as _middleware_mod
from shared.middleware import internal_auth as _internal_auth_mod


def _make_app():
    app = FastAPI()

    @app.get("/test")
    async def t():
        return {"ok": True}

    @app.get("/health")
    async def h():
        return {"status": "alive"}

    from shared.middleware import APIKeyMiddleware

    app.add_middleware(APIKeyMiddleware)
    return app


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw_headers})


@pytest.fixture(autouse=True)
def reset_middleware_state():
    """Reset class-level state before each test."""
    from shared.middleware import APIKeyMiddleware

    APIKeyMiddleware._auth_disabled_logged = False
    APIKeyMiddleware._auth_misconfigured_logged = False
    yield
    APIKeyMiddleware._auth_disabled_logged = False
    APIKeyMiddleware._auth_misconfigured_logged = False


def test_api_key_valid():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = "test-key"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


def test_api_key_invalid():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = "test-key"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401


def test_api_key_missing():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = "test-key"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 401


def test_api_key_skip_health():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = "test-key"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}


def test_api_key_disabled_allows_all():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = ""
        mock_settings.app_env = "development"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


def test_api_key_disabled_logs_once():
    with (
        patch.object(_middleware_mod, "settings") as mock_settings,
        patch.object(_middleware_mod, "logger") as mock_logger,
    ):
        mock_settings.pm_api_key = ""
        mock_settings.app_env = "development"
        app = _make_app()
        client = TestClient(app)

        # First request should trigger the warning
        client.get("/test")
        # Second request should NOT trigger it again
        client.get("/test")

        warning_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "api_key_auth_disabled"
        ]
        assert len(warning_calls) == 1


def test_api_key_empty_fails_closed_in_production():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = ""
        mock_settings.app_env = "production"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 503


def test_api_key_empty_still_skips_health_in_production():
    with patch.object(_middleware_mod, "settings") as mock_settings:
        mock_settings.pm_api_key = ""
        mock_settings.app_env = "production"
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_internal_key_empty_fails_closed_in_production():
    with patch.object(_internal_auth_mod, "settings") as mock_settings:
        mock_settings.internal_service_key = ""
        mock_settings.app_env = "production"
        with pytest.raises(HTTPException) as exc_info:
            await _internal_auth_mod.verify_internal_key(_make_request())
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_internal_key_empty_allows_dev_mode():
    with patch.object(_internal_auth_mod, "settings") as mock_settings:
        mock_settings.internal_service_key = ""
        mock_settings.app_env = "development"
        assert await _internal_auth_mod.verify_internal_key(_make_request()) is None
