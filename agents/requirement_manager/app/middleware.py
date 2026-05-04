"""
Production middleware stack — Security, Tracing, Access Logging, Rate Limiting.
"""
import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.config import settings
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("middleware")


# ---------------------------------------------------------------------------
# 1. Security Headers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 2. Request Tracing
# ---------------------------------------------------------------------------

class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Propagate or generate request_id / trace_id for every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Trace-ID")
            or uuid.uuid4().hex
        )
        trace_id = request.headers.get("X-Trace-ID", request_id)

        structlog.contextvars.bind_contextvars(
            request_id=request_id, trace_id=trace_id
        )

        request.state.request_id = request_id
        request.state.trace_id = trace_id

        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "trace_id")


# ---------------------------------------------------------------------------
# 3. Access Logging
# ---------------------------------------------------------------------------

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
                client_ip_hash=hash_identifier(client_ip),
            )

            if status < 400:
                logger.info("access", **log_data)
            elif status < 500:
                logger.warning("access", **log_data)
            else:
                logger.error("access", **log_data)


# ---------------------------------------------------------------------------
# 4. Rate Limiting
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client-IP rate limiting."""

    EXEMPT_PATHS = {"/health", "/health/ready", "/metrics"}

    def __init__(self, app):
        super().__init__(app)
        self._requests_per_window = settings.rate_limit_requests
        self._window_seconds = settings.rate_limit_window_seconds
        self._requests: dict[str, list[float]] = {}
        self._last_gc = time.time()
        self._gc_interval = 300  # purge stale keys every 5 min

    def _maybe_gc(self, now: float) -> None:
        """Purge keys with no recent requests to prevent memory leak."""
        if now - self._last_gc < self._gc_interval:
            return
        self._last_gc = now
        window_start = now - self._window_seconds
        stale = [k for k, v in self._requests.items() if not v or v[-1] <= window_start]
        for k in stale:
            del self._requests[k]

    def _is_allowed(self, key: str) -> bool:
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

    def _retry_after(self, key: str) -> int:
        if key not in self._requests or not self._requests[key]:
            return 0
        oldest = self._requests[key][0]
        return max(1, int(oldest + self._window_seconds - time.time()) + 1)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if not self._is_allowed(client_ip):
            retry_after = self._retry_after(client_ip)
            logger.warning(
                "rate_limited",
                client_ip_hash=hash_identifier(client_ip),
                retry_after=retry_after,
            )
            return Response(
                content='{"detail":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
