"""AgentForge Orchestrator HTTP API client."""
from __future__ import annotations

import time
from typing import Any

import httpx

from shared.infra.circuit_breaker import CircuitBreaker

from ..app.metrics import CIRCUIT_BREAKER_STATE, FORGE_API_LATENCY, FORGE_POLL_ERRORS
from ..models.schemas import WorkflowPlan


class ForgeClientError(Exception):
    pass


class ForgeClient:
    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=30, write=10, pool=5),
            limits=httpx.Limits(max_connections=10),
        )
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5, recovery_timeout=60, name="agentforge"
        )

    async def create_workflow(self, plan: WorkflowPlan) -> str:
        data = await self._request("POST", "/api/v1/workflows", json=plan.model_dump())
        workflow_id = data.get("workflow", {}).get("id")
        if not workflow_id:
            raise ForgeClientError(
                f"AgentForge returned no workflow ID. Response: {list(data.keys())}"
            )
        return workflow_id

    async def run_workflow(self, workflow_id: str) -> None:
        await self._request("POST", f"/api/v1/workflows/{workflow_id}/run")

    async def get_status(self, workflow_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/workflows/{workflow_id}/status")

    async def signal(self, workflow_id: str, node_id: str, decision: str) -> None:
        await self._request(
            "POST",
            f"/api/v1/workflows/{workflow_id}/signal",
            json={"nodeId": node_id, "decision": decision},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self._circuit_breaker.can_execute():
            CIRCUIT_BREAKER_STATE.labels(target="agentforge").set(1)
            raise ForgeClientError("AgentForge circuit breaker is open")
        url = f"{self._base_url}{path}"
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        start = time.monotonic()
        try:
            response = await self._client.request(method, url, headers=headers, **kwargs)
            elapsed = time.monotonic() - start
            FORGE_API_LATENCY.observe(elapsed)
            if response.status_code >= 500:
                self._circuit_breaker.record_failure()
                FORGE_POLL_ERRORS.inc()
                raise ForgeClientError(
                    f"AgentForge {response.status_code}: {response.text[:200]}"
                )
            if response.status_code >= 400:
                FORGE_POLL_ERRORS.inc()
                raise ForgeClientError(
                    f"AgentForge {response.status_code}: {response.text[:200]}"
                )
            self._circuit_breaker.record_success()
            CIRCUIT_BREAKER_STATE.labels(target="agentforge").set(0)
            return response.json()
        except httpx.HTTPError as e:
            elapsed = time.monotonic() - start
            FORGE_API_LATENCY.observe(elapsed)
            self._circuit_breaker.record_failure()
            FORGE_POLL_ERRORS.inc()
            raise ForgeClientError(f"HTTP error: {e}") from e
