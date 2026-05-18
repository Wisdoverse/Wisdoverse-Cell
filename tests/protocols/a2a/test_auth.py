"""Tests for A2A auth error contracts."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from shared.api import ApiErrorCode
from shared.protocols.a2a.middleware import auth as a2a_auth
from shared.protocols.a2a.middleware.auth import A2AAuthContext


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/a2a/rpc",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def test_decode_invalid_jwt_uses_error_contract() -> None:
    with pytest.raises(HTTPException) as exc_info:
        a2a_auth.decode_jwt_token("not-a-jwt")

    exc = exc_info.value
    assert exc.status_code == 401
    assert str(exc.detail).startswith("Invalid token:")
    assert exc.headers["WWW-Authenticate"] == "Bearer"
    assert exc.headers["X-Error-Code"] == ApiErrorCode.A2A_AUTH_INVALID_TOKEN.value


@pytest.mark.asyncio
async def test_get_auth_context_missing_auth_uses_error_contract() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await a2a_auth.get_auth_context(_make_request(), bearer=None, api_key=None)

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail == "Missing or invalid authentication"
    assert exc.headers["WWW-Authenticate"] == "Bearer"
    assert (
        exc.headers["X-Error-Code"]
        == ApiErrorCode.A2A_AUTH_MISSING_OR_INVALID.value
    )


@pytest.mark.asyncio
async def test_require_scope_missing_scope_uses_error_contract() -> None:
    dependency = a2a_auth.require_scope("a2a:write")
    auth_context = A2AAuthContext(
        agent_id="caller-agent",
        scopes=["a2a:read"],
        auth_method="api_key",
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(auth_context)

    exc = exc_info.value
    assert exc.status_code == 403
    assert exc.detail == "Missing required scope: a2a:write"
    assert exc.headers["X-Error-Code"] == ApiErrorCode.A2A_MISSING_REQUIRED_SCOPE.value


@pytest.mark.asyncio
async def test_check_rate_limit_exceeded_uses_error_contract() -> None:
    class BlockedLimiter:
        def is_allowed(self, key: str) -> bool:
            return False

        def get_retry_after(self, key: str) -> int:
            return 7

    with patch.object(a2a_auth, "rate_limiter", BlockedLimiter()):
        with pytest.raises(HTTPException) as exc_info:
            await a2a_auth.check_rate_limit(_make_request(), auth=None)

    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.detail == "Rate limit exceeded"
    assert exc.headers["Retry-After"] == "7"
    assert exc.headers["X-Error-Code"] == ApiErrorCode.A2A_RATE_LIMIT_EXCEEDED.value
