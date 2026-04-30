"""
Inter-agent HTTP client for decoupled communication.

Provides a thin async wrapper around httpx for calling other agents' REST APIs,
with typed convenience clients for specific agents.
"""

from __future__ import annotations

import httpx

from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class AgentClient:
    """Thin async HTTP client for calling other agents' REST APIs."""

    def __init__(self, base_url: str, timeout: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if settings.internal_service_key:
            headers["X-Internal-Key"] = settings.internal_service_key
        return headers

    async def post(self, path: str, json: dict | None = None) -> dict:
        """Send a POST request and return the JSON response."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=json, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def get(self, path: str) -> dict:
        """Send a GET request and return the JSON response."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()


class PMAgentClient:
    """Typed client for pjm_agent's decomposition API."""

    def __init__(self, base_url: str | None = None) -> None:
        url = base_url or settings.pjm_agent_url
        self._client = AgentClient(url)

    async def approve_decomposition(self, wp_id: int, operator: str) -> dict | None:
        """Approve a work-package decomposition. Returns None on 404."""
        try:
            return await self._client.post(
                f"/api/v1/pm/decompose/{wp_id}/approve",
                json={"operator": operator},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise

    async def reject_decomposition(
        self, wp_id: int, operator: str, reason: str = ""
    ) -> dict | None:
        """Reject a work-package decomposition. Returns None on 404."""
        try:
            return await self._client.post(
                f"/api/v1/pm/decompose/{wp_id}/reject",
                json={"operator": operator, "reason": reason},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise

    async def retry_decomposition(self, wp_id: int) -> dict | None:
        """Retry a failed decomposition. Returns None on 404."""
        try:
            return await self._client.post(f"/api/v1/pm/decompose/{wp_id}/retry")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise

    async def get_decomposition(self, wp_id: int) -> dict | None:
        """Get decomposition status. Returns None on 404."""
        try:
            return await self._client.get(f"/api/v1/pm/decompose/{wp_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Decomposition not found for wp_id=%s", wp_id)
                return None
            raise
