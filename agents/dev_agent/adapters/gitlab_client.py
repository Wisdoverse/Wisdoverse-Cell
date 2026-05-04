"""GitLab API client for MR creation."""
from __future__ import annotations

from typing import Any

import httpx

from shared.infra.circuit_breaker import CircuitBreaker
from shared.utils.logger import get_logger

from ..app.metrics import CIRCUIT_BREAKER_STATE, MR_CREATION_ERRORS

logger = get_logger("dev_agent.gitlab")


class GitLabClientError(Exception):
    pass


class GitLabClient:
    def __init__(self, base_url: str, token: str, project_id: int):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._project_id = project_id
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=30, write=10, pool=5),
            limits=httpx.Limits(max_connections=5),
        )
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=120, name="gitlab"
        )

    async def create_mr(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a merge request. Returns {url, iid, web_url}."""
        data = await self._request(
            "POST",
            f"/api/v4/projects/{self._project_id}/merge_requests",
            json={
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
                "remove_source_branch": True,
            },
        )
        return {
            "iid": data.get("iid"),
            "web_url": data.get("web_url", ""),
            "url": data.get("web_url", ""),
        }

    async def check_existing_mr(self, source_branch: str) -> dict | None:
        """Check if an open MR already exists for this branch (idempotency)."""
        try:
            data = await self._request(
                "GET",
                f"/api/v4/projects/{self._project_id}/merge_requests",
                params={"source_branch": source_branch, "state": "opened"},
            )
            if isinstance(data, list) and len(data) > 0:
                mr = data[0]
                return {"iid": mr.get("iid"), "web_url": mr.get("web_url", "")}
        except GitLabClientError as e:
            logger.warning(
                "check_existing_mr_failed",
                source_branch=source_branch,
                error=str(e),
                exc_info=True,
            )
        return None

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        if not self._circuit_breaker.can_execute():
            CIRCUIT_BREAKER_STATE.labels(target="gitlab").set(1)
            raise GitLabClientError("GitLab circuit breaker is open")

        url = f"{self._base_url}{path}"
        headers = {"PRIVATE-TOKEN": self._token}
        try:
            response = await self._client.request(
                method, url, headers=headers, **kwargs
            )
            if response.status_code >= 500:
                self._circuit_breaker.record_failure()
                MR_CREATION_ERRORS.inc()
                raise GitLabClientError(
                    f"GitLab {response.status_code}: {response.text[:200]}"
                )
            if response.status_code >= 400:
                MR_CREATION_ERRORS.inc()
                raise GitLabClientError(
                    f"GitLab {response.status_code}: {response.text[:200]}"
                )
            self._circuit_breaker.record_success()
            CIRCUIT_BREAKER_STATE.labels(target="gitlab").set(0)
            return response.json()
        except httpx.HTTPError as e:
            self._circuit_breaker.record_failure()
            MR_CREATION_ERRORS.inc()
            raise GitLabClientError(f"HTTP error: {e}") from e
