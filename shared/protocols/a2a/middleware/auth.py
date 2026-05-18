"""
A2A Authentication Middleware

JWT and API Key authentication for A2A protocol.
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from shared.api import (
    raise_a2a_auth_invalid_token,
    raise_a2a_auth_missing_or_invalid,
    raise_a2a_auth_token_expired,
    raise_a2a_missing_required_scope,
    raise_a2a_rate_limit_exceeded,
)
from shared.config import settings


class TokenPayload(BaseModel):
    """JWT token payload."""

    model_config = ConfigDict(extra="allow")

    sub: str = Field(..., description="Subject (agent ID)")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
    scopes: list[str] = Field(default_factory=list, description="Granted scopes")
    agent_name: str | None = Field(None, description="Agent display name")


class A2AAuthContext(BaseModel):
    """Authentication context passed to handlers."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Authenticated agent ID")
    agent_name: str | None = Field(None, description="Agent display name")
    scopes: list[str] = Field(default_factory=list, description="Granted scopes")
    auth_method: str = Field(..., description="Authentication method used")


# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(
    name=settings.a2a_api_key_header,
    auto_error=False,
)


def create_jwt_token(
    agent_id: str,
    scopes: list[str] | None = None,
    agent_name: str | None = None,
    expiry_minutes: int | None = None,
) -> str:
    """
    Create a JWT token for A2A authentication.

    Args:
        agent_id: The agent identifier.
        scopes: List of granted scopes (e.g., ["a2a:read", "a2a:write"]).
        agent_name: Optional agent display name.
        expiry_minutes: Token expiry in minutes (defaults to config).

    Returns:
        Encoded JWT token string.
    """
    if expiry_minutes is None:
        expiry_minutes = settings.a2a_jwt_expiry_minutes

    now = datetime.now(UTC)
    payload = TokenPayload(
        sub=agent_id,
        exp=int((now + timedelta(minutes=expiry_minutes)).timestamp()),
        iat=int(now.timestamp()),
        scopes=scopes or ["a2a:read"],
        agent_name=agent_name,
    )

    return jwt.encode(
        payload.model_dump(exclude_none=True),
        settings.a2a_jwt_secret.get_secret_value(),
        algorithm=settings.a2a_jwt_algorithm,
    )


def decode_jwt_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string.

    Returns:
        Decoded token payload.

    Raises:
        HTTPException: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.a2a_jwt_secret.get_secret_value(),
            algorithms=[settings.a2a_jwt_algorithm],
        )
        return TokenPayload.model_validate(payload)
    except jwt.ExpiredSignatureError:
        raise_a2a_auth_token_expired()
    except jwt.InvalidTokenError as e:
        raise_a2a_auth_invalid_token(str(e))


# API Key storage (in production, use Redis or database)
_api_keys: dict[str, dict[str, Any]] = {}


def register_api_key(
    api_key: str,
    agent_id: str,
    scopes: list[str] | None = None,
    agent_name: str | None = None,
) -> None:
    """
    Register an API key for an agent.

    Args:
        api_key: The API key to register.
        agent_id: The agent identifier.
        scopes: List of granted scopes.
        agent_name: Optional agent display name.
    """
    _api_keys[api_key] = {
        "agent_id": agent_id,
        "scopes": scopes or ["a2a:read"],
        "agent_name": agent_name,
    }


def validate_api_key(api_key: str) -> dict[str, Any] | None:
    """
    Validate an API key.

    Args:
        api_key: The API key to validate.

    Returns:
        Key metadata if valid, None otherwise.
    """
    return _api_keys.get(api_key)


async def get_auth_context(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_header),
) -> A2AAuthContext:
    """
    FastAPI dependency for A2A authentication.

    Supports both JWT Bearer tokens and API keys.
    """
    # Try Bearer token first
    if bearer is not None:
        payload = decode_jwt_token(bearer.credentials)
        return A2AAuthContext(
            agent_id=payload.sub,
            agent_name=payload.agent_name,
            scopes=payload.scopes,
            auth_method="bearer",
        )

    # Try API key
    if api_key is not None and settings.a2a_api_key_enabled:
        key_data = validate_api_key(api_key)
        if key_data is not None:
            return A2AAuthContext(
                agent_id=key_data["agent_id"],
                agent_name=key_data.get("agent_name"),
                scopes=key_data.get("scopes", ["a2a:read"]),
                auth_method="api_key",
            )

    # No valid auth
    raise_a2a_auth_missing_or_invalid()


async def get_optional_auth_context(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_header),
) -> A2AAuthContext | None:
    """
    FastAPI dependency for optional A2A authentication.

    Returns None if no valid auth is provided.
    """
    # Try Bearer token first
    if bearer is not None:
        try:
            payload = decode_jwt_token(bearer.credentials)
            return A2AAuthContext(
                agent_id=payload.sub,
                agent_name=payload.agent_name,
                scopes=payload.scopes,
                auth_method="bearer",
            )
        except HTTPException:
            pass

    # Try API key
    if api_key is not None and settings.a2a_api_key_enabled:
        key_data = validate_api_key(api_key)
        if key_data is not None:
            return A2AAuthContext(
                agent_id=key_data["agent_id"],
                agent_name=key_data.get("agent_name"),
                scopes=key_data.get("scopes", ["a2a:read"]),
                auth_method="api_key",
            )

    return None


def require_scope(required_scope: str):
    """
    Decorator factory for scope-based authorization.

    Usage:
        @router.post("/protected")
        async def protected_endpoint(
            auth: A2AAuthContext = Depends(require_scope("a2a:write"))
        ):
            ...
    """

    async def dependency(
        auth: A2AAuthContext = Depends(get_auth_context),
    ) -> A2AAuthContext:
        if required_scope not in auth.scopes:
            raise_a2a_missing_required_scope(required_scope)
        return auth

    return dependency


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(
        self,
        requests_per_window: int | None = None,
        window_seconds: int | None = None,
    ):
        self._requests_per_window = (
            requests_per_window or settings.a2a_rate_limit_requests
        )
        self._window_seconds = window_seconds or settings.a2a_rate_limit_window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """
        Check if a request is allowed for the given key.

        Args:
            key: Rate limit key (e.g., agent_id or IP).

        Returns:
            True if request is allowed, False otherwise.
        """
        now = time.time()
        window_start = now - self._window_seconds

        # Get requests in current window
        if key not in self._requests:
            self._requests[key] = []

        # Remove expired requests
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        # Check limit
        if len(self._requests[key]) >= self._requests_per_window:
            return False

        # Record request
        self._requests[key].append(now)
        return True

    def get_retry_after(self, key: str) -> int:
        """
        Get seconds until next request is allowed.

        Args:
            key: Rate limit key.

        Returns:
            Seconds to wait, or 0 if request is allowed.
        """
        if key not in self._requests or not self._requests[key]:
            return 0

        oldest = min(self._requests[key])
        return max(0, int(oldest + self._window_seconds - time.time()))


# Global rate limiter instance
rate_limiter = RateLimiter()


async def check_rate_limit(
    request: Request,
    auth: A2AAuthContext | None = Depends(get_optional_auth_context),
) -> None:
    """
    FastAPI dependency for rate limiting.

    Uses agent_id if authenticated, otherwise uses client IP.
    """
    # Determine rate limit key
    key = auth.agent_id if auth else request.client.host if request.client else "unknown"

    if not rate_limiter.is_allowed(key):
        retry_after = rate_limiter.get_retry_after(key)
        raise_a2a_rate_limit_exceeded(retry_after)
