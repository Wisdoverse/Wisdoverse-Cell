from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import shared.middleware as _middleware_mod


@pytest.fixture(autouse=True)
def _patch_settings():
    """Patch middleware settings for all tests in this module."""
    mock_settings = MagicMock()
    mock_settings.rate_limit_requests = 5
    mock_settings.rate_limit_window_seconds = 60
    mock_settings.redis_url = "redis://localhost:63999/0"  # Unreachable → forces fallback
    mock_settings.pm_api_key = ""
    with patch.object(_middleware_mod, "settings", mock_settings):
        yield mock_settings


def _build_app(rate_limit_requests=5):
    """Build a test app with rate limiting."""
    _middleware_mod.settings.rate_limit_requests = rate_limit_requests

    app = FastAPI()
    app.add_middleware(_middleware_mod.RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "alive"}

    return app


def test_health_exempt_from_rate_limit():
    """Health endpoints should never be rate limited."""
    app = _build_app(rate_limit_requests=1)
    client = TestClient(app)
    for _ in range(10):
        r = client.get("/health")
        assert r.status_code == 200


def test_rate_limit_returns_429_with_retry_after():
    """After exceeding limit, should return 429 with Retry-After header."""
    app = _build_app(rate_limit_requests=2)
    client = TestClient(app)
    assert client.get("/test").status_code == 200
    assert client.get("/test").status_code == 200
    r = client.get("/test")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_rate_limit_allows_within_limit():
    """Requests within limit should pass."""
    app = _build_app(rate_limit_requests=10)
    client = TestClient(app)
    for _ in range(10):
        r = client.get("/test")
        assert r.status_code == 200
