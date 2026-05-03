"""
Production middleware stack — Security, Tracing, Access Logging, Rate Limiting.

Shared across all agent services. Extracted from the requirement manager agent
middleware pattern.
"""

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger("middleware")


def _is_production() -> bool:
    return settings.app_env.lower() in {"production", "prod"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header for non-public endpoints."""

    SKIP_PATHS = {
        "/health",
        "/health/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/webhook/feishu",
    }

    _auth_disabled_logged: bool = False
    _auth_misconfigured_logged: bool = False

    async def dispatch(self, request: Request, call_next):
        # Skip validation for public paths
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        if not settings.pm_api_key:
            if _is_production():
                if not APIKeyMiddleware._auth_misconfigured_logged:
                    logger.error("api_key_auth_misconfigured", reason="pm_api_key is empty")
                    APIKeyMiddleware._auth_misconfigured_logged = True
                return Response(
                    content='{"detail":"API key authentication is not configured"}',
                    status_code=503,
                    media_type="application/json",
                )
            if not APIKeyMiddleware._auth_disabled_logged:
                logger.warning(
                    "api_key_auth_disabled", reason="pm_api_key is empty, all requests allowed"
                )
                APIKeyMiddleware._auth_disabled_logged = True
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key or api_key != settings.pm_api_key:
            logger.warning(
                "api_key_rejected",
                path=request.url.path,
                client_ip=request.client.host if request.client else "unknown",
            )
            return Response(
                content='{"detail":"Invalid or missing API key"}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject OWASP security headers into every response."""

    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for header, value in self.HEADERS.items():
            response.headers[header] = value
        return response


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Propagate or generate request_id / trace_id for every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Trace-ID")
            or uuid.uuid4().hex
        )
        trace_id = request.headers.get("X-Trace-ID", request_id)

        structlog.contextvars.bind_contextvars(request_id=request_id, trace_id=trace_id)

        request.state.request_id = request_id
        request.state.trace_id = trace_id

        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "trace_id")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Structured access log with latency, status, and content-length."""

    SKIP_PATHS = {"/health", "/health/ready", "/metrics"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        status = 500
        content_length = 0

        try:
            response: Response = await call_next(request)
            status = response.status_code
            content_length = response.headers.get("content-length", 0)
            return response
        except Exception:
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            client_ip = request.client.host if request.client else "unknown"

            log_data = dict(
                method=request.method,
                path=request.url.path,
                status=status,
                latency_ms=latency_ms,
                content_length=content_length,
                client_ip=client_ip,
            )

            if status < 400:
                logger.info("access", **log_data)
            elif status < 500:
                logger.warning("access", **log_data)
            else:
                logger.error("access", **log_data)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client-IP rate limiting with Redis backend (in-memory fallback)."""

    EXEMPT_PATHS = {"/health", "/health/ready", "/metrics"}

    def __init__(self, app):
        super().__init__(app)
        self._requests_per_window = settings.rate_limit_requests
        self._window_seconds = settings.rate_limit_window_seconds
        # In-memory fallback
        self._requests: dict[str, list[float]] = {}
        self._last_gc = time.time()
        self._gc_interval = 300
        # Redis (lazy init on first request, retry on transient failure)
        self._redis = None
        self._redis_next_retry: float = 0  # monotonic timestamp for next retry

    async def _get_redis(self):
        now = time.monotonic()
        if self._redis is not None:
            return self._redis
        if now < self._redis_next_retry:
            return None
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
            await client.ping()
            self._redis = client
            return self._redis
        except Exception as exc:
            logger.info("rate_limit_redis_unavailable", error=str(exc))
            self._redis_next_retry = now + 30  # Retry after 30s
            return None

    async def _is_allowed_redis(self, key: str) -> tuple[bool, int]:
        """Check rate limit via Redis INCR + EXPIRE. Returns (allowed, retry_after)."""
        r = await self._get_redis()
        if r is None:
            allowed = self._is_allowed_memory(key)
            retry_after = 0 if allowed else self._retry_after_memory(key)
            return allowed, retry_after
        try:
            window = int(time.time()) // self._window_seconds
            redis_key = f"ratelimit:{key}:{window}"
            count = await r.incr(redis_key)
            if count == 1:
                await r.expire(redis_key, self._window_seconds)
            if count > self._requests_per_window:
                retry_after = self._window_seconds - (int(time.time()) % self._window_seconds)
                return False, max(1, retry_after)
            return True, 0
        except Exception as exc:
            logger.warning("rate_limit_redis_error", error=str(exc))
            allowed = self._is_allowed_memory(key)
            retry_after = 0 if allowed else self._retry_after_memory(key)
            return allowed, retry_after

    # ── In-memory fallback ─────────────────────────────────────────────────

    def _maybe_gc(self, now: float) -> None:
        if now - self._last_gc < self._gc_interval:
            return
        self._last_gc = now
        window_start = now - self._window_seconds
        stale = [k for k, v in self._requests.items() if not v or v[-1] <= window_start]
        for k in stale:
            del self._requests[k]

    def _is_allowed_memory(self, key: str) -> bool:
        now = time.time()
        self._maybe_gc(now)
        window_start = now - self._window_seconds
        if key not in self._requests:
            self._requests[key] = []
        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        if len(self._requests[key]) >= self._requests_per_window:
            return False
        self._requests[key].append(now)
        return True

    def _retry_after_memory(self, key: str) -> int:
        if key not in self._requests or not self._requests[key]:
            return 0
        oldest = self._requests[key][0]
        return max(1, int(oldest + self._window_seconds - time.time()) + 1)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        allowed, retry_after = await self._is_allowed_redis(client_ip)
        if not allowed:
            logger.warning("rate_limited", client_ip=client_ip, retry_after=retry_after)
            return Response(
                content='{"detail":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
