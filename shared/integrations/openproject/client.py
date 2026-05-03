"""
OpenProject API Client

Async OpenProject REST API client based on httpx, with retry and optimistic lock
support.
"""
import asyncio
from typing import Any, Optional

import httpx

from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger("openproject.client")

MAX_RETRIES = 3
RETRY_DELAY = 1.0
RETRY_BACKOFF = 2.0
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class OpenProjectClient:
    """OpenProject API client with Basic Auth and retry."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or settings.openproject_url).rstrip("/")
        self.api_key = api_key or settings.openproject_api_key.get_secret_value()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=("apikey", self.api_key),
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Execute HTTP request with retry logic."""
        client = await self._get_client()
        last_exc = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.request(method, path, **kwargs)
                if resp.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                    logger.warning("op_request_retry", method=method, path=path,
                                   status=resp.status_code, attempt=attempt + 1, delay=delay)
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                    logger.warning("op_request_retry", method=method, path=path,
                                   error=str(e), attempt=attempt + 1, delay=delay)
                    await asyncio.sleep(delay)
                else:
                    logger.error("op_request_failed", method=method, path=path, error=str(e))
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in RETRYABLE_STATUS_CODES:
                    # Include response body for meaningful error messages (e.g. OP 422 details)
                    try:
                        body = e.response.json()
                        msg = body.get("message", e.response.text)
                    except Exception:
                        msg = e.response.text
                    raise httpx.HTTPStatusError(
                        message=f"{method} {path} → {e.response.status_code}: {msg}",
                        request=e.request,
                        response=e.response,
                    ) from None
                last_exc = e

        raise last_exc or Exception(f"Request {method} {path} failed after {MAX_RETRIES} attempts")

    async def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("POST", path, json=data)
        return resp.json()

    async def patch(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("PATCH", path, json=data)
        return resp.json()

    async def delete(self, path: str) -> None:
        await self._request("DELETE", path)

    # ============ Business methods ============

    async def get_work_packages(
        self,
        project_id: int | None = None,
        filters: str | None = None,
        page_size: int = 100,
    ) -> list[dict]:
        """Get work packages."""
        params: dict[str, Any] = {"pageSize": page_size}
        if filters:
            params["filters"] = filters
        path = f"/api/v3/projects/{project_id}/work_packages" if project_id else "/api/v3/work_packages"
        result = await self.get(path, params=params)
        return result.get("_embedded", {}).get("elements", [])

    async def get_work_package(self, wp_id: int) -> dict:
        """Get one work package."""
        return await self.get(f"/api/v3/work_packages/{wp_id}")

    async def update_work_package(self, wp_id: int, data: dict[str, Any]) -> dict:
        """Update a work package and handle lockVersion automatically."""
        current = await self.get_work_package(wp_id)
        data["lockVersion"] = current["lockVersion"]
        return await self.patch(f"/api/v3/work_packages/{wp_id}", data)

    async def create_work_package(self, project_id: int, data: dict[str, Any]) -> dict:
        """Create a work package under a project."""
        return await self.post(f"/api/v3/projects/{project_id}/work_packages", data)

    async def get_project(self, project_id: int) -> dict:
        """Get project information."""
        return await self.get(f"/api/v3/projects/{project_id}")

    async def test_connection(self) -> bool:
        """Test API connectivity."""
        try:
            await self.get("/api/v3")
            return True
        except Exception:
            return False


def get_op_client() -> OpenProjectClient:
    """Get the OpenProjectClient singleton."""
    return _op_client


_op_client = OpenProjectClient()
