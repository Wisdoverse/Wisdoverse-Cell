"""
Inter-agent HTTP client for decoupled communication.

Provides a thin async wrapper around httpx for calling other agents' REST APIs,
with typed convenience clients for specific agents.
"""

from __future__ import annotations

from enum import Enum

import httpx

from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class AgentClientErrorCategory(str, Enum):
    """Stable error categories for inter-agent HTTP calls."""

    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    NETWORK = "network"
    AUTH = "auth"
    CONTENT_SIZE = "content_size"
    OTHER = "other"


_AUTH_STATUS_CODES = {401, 403}
_CONTENT_SIZE_STATUS_CODES = {413, 414, 431}
_OVERLOADED_STATUS_CODES = {500, 502, 503, 504, 529}

_RETRY_DECISIONS = {
    AgentClientErrorCategory.RATE_LIMIT: "retry_with_backoff",
    AgentClientErrorCategory.OVERLOADED: "retry_with_backoff",
    AgentClientErrorCategory.NETWORK: "retry_with_backoff",
    AgentClientErrorCategory.AUTH: "do_not_retry_until_auth_is_fixed",
    AgentClientErrorCategory.CONTENT_SIZE: "do_not_retry_until_payload_is_reduced",
    AgentClientErrorCategory.OTHER: "do_not_retry_without_investigation",
}

_OPERATOR_ACTIONS = {
    AgentClientErrorCategory.RATE_LIMIT: "reduce_call_rate_or_check_target_quota",
    AgentClientErrorCategory.OVERLOADED: "check_target_service_health",
    AgentClientErrorCategory.NETWORK: "check_service_discovery_and_network_path",
    AgentClientErrorCategory.AUTH: "check_internal_service_key_and_target_auth_policy",
    AgentClientErrorCategory.CONTENT_SIZE: "reduce_payload_or_use_artifact_reference",
    AgentClientErrorCategory.OTHER: "inspect_target_logs_with_trace_id",
}


def classify_agent_client_error(exc: BaseException) -> AgentClientErrorCategory:
    """Map an inter-agent HTTP failure into a stable operator category."""
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in _AUTH_STATUS_CODES:
            return AgentClientErrorCategory.AUTH
        if status_code == 429:
            return AgentClientErrorCategory.RATE_LIMIT
        if status_code in _CONTENT_SIZE_STATUS_CODES:
            return AgentClientErrorCategory.CONTENT_SIZE
        if status_code in _OVERLOADED_STATUS_CODES:
            return AgentClientErrorCategory.OVERLOADED
        return AgentClientErrorCategory.OTHER

    if isinstance(exc, httpx.RequestError):
        return AgentClientErrorCategory.NETWORK

    return AgentClientErrorCategory.OTHER


class AgentClient:
    """Thin async HTTP client for calling other agents' REST APIs."""

    def __init__(self, base_url: str, timeout: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self, trace_id: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if settings.internal_service_key:
            headers["X-Internal-Key"] = settings.internal_service_key
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        return headers

    def _log_error(
        self,
        *,
        method: str,
        path: str,
        exc: httpx.HTTPError,
        trace_id: str | None,
    ) -> None:
        category = classify_agent_client_error(exc)
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        logger.warning(
            "agent_http_request_failed",
            method=method,
            base_url=self.base_url,
            path=path,
            error_category=category.value,
            retry_decision=_RETRY_DECISIONS[category],
            operator_action=_OPERATOR_ACTIONS[category],
            status_code=status_code,
            trace_id=trace_id,
        )

    async def post(
        self,
        path: str,
        json: dict | None = None,
        *,
        trace_id: str | None = None,
    ) -> dict:
        """Send a POST request and return the JSON response."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(url, json=json, headers=self._headers(trace_id))
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                self._log_error(method="POST", path=path, exc=exc, trace_id=trace_id)
                raise

    async def get(self, path: str, *, trace_id: str | None = None) -> dict:
        """Send a GET request and return the JSON response."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(url, headers=self._headers(trace_id))
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                self._log_error(method="GET", path=path, exc=exc, trace_id=trace_id)
                raise


class PMAgentClient:
    """Typed client for pjm_agent's decomposition API."""

    def __init__(self, base_url: str | None = None) -> None:
        url = base_url or settings.pjm_agent_url
        self._client = AgentClient(url)

    async def approve_decomposition(
        self,
        wp_id: int,
        operator: str,
        *,
        trace_id: str | None = None,
    ) -> dict | None:
        """Approve a work-package decomposition. Returns None on 404."""
        try:
            return await self._client.post(
                f"/api/v1/pm/decompose/{wp_id}/approve",
                json={"operator": operator},
                trace_id=trace_id,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise

    async def reject_decomposition(
        self,
        wp_id: int,
        operator: str,
        reason: str = "",
        *,
        trace_id: str | None = None,
    ) -> dict | None:
        """Reject a work-package decomposition. Returns None on 404."""
        try:
            return await self._client.post(
                f"/api/v1/pm/decompose/{wp_id}/reject",
                json={"operator": operator, "reason": reason},
                trace_id=trace_id,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise

    async def retry_decomposition(
        self,
        wp_id: int,
        *,
        trace_id: str | None = None,
    ) -> dict | None:
        """Retry a failed decomposition. Returns None on 404."""
        try:
            return await self._client.post(
                f"/api/v1/pm/decompose/{wp_id}/retry",
                trace_id=trace_id,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise

    async def get_decomposition(
        self,
        wp_id: int,
        *,
        trace_id: str | None = None,
    ) -> dict | None:
        """Get decomposition status. Returns None on 404."""
        try:
            return await self._client.get(
                f"/api/v1/pm/decompose/{wp_id}",
                trace_id=trace_id,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise
