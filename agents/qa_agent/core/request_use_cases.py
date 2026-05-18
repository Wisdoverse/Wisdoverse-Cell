"""Application use cases for QA agent requests."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core import request_error, unknown_action_error

from ..models.schemas import AcceptanceExecutionResult, QARunRequest, QARunStats


class QARequestAgentPort(Protocol):
    """QA operations required by agent request handling."""

    async def run_acceptance(
        self,
        request: QARunRequest,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> AcceptanceExecutionResult:
        """Run one acceptance check."""

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List acceptance run records."""

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one acceptance run record."""

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        """Return acceptance run statistics."""


class QARequestUseCase:
    """Dispatch and execute QA agent request actions."""

    def __init__(self, agent: QARequestAgentPort):
        self._agent = agent

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "run":
            run_request = QARunRequest(
                agent_name=request["agent_name"],
                level=request.get("level", "all"),
                commit_sha=request.get("commit_sha"),
                mr_iid=request.get("mr_iid"),
                gitlab_project_id=request.get("gitlab_project_id"),
                trigger="api",
                requested_by=request.get("requested_by", "api"),
            )
            result = await self._agent.run_acceptance(run_request)
            return result.raw_report
        if action == "list_runs":
            runs = await self._agent.list_runs(
                agent_name=request.get("agent_name"),
                limit=request.get("limit", 20),
                offset=request.get("offset", 0),
            )
            return {"items": runs}
        if action == "get_run":
            run = await self._agent.get_run(request["run_id"])
            return run or request_error("not found", "qa_run_not_found")
        if action == "stats":
            stats = await self._agent.get_stats(
                agent_name=request.get("agent_name"),
                days=request.get("days", 30),
            )
            return stats.model_dump()
        return unknown_action_error()
