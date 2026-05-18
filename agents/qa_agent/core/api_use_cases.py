"""Application use cases for QA HTTP operations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from ..models.schemas import AcceptanceExecutionResult, QARunRequest, QARunStats


class QAApiAgentPort(Protocol):
    """Agent operations required by the QA HTTP application use cases."""

    async def run_acceptance(
        self,
        request: QARunRequest,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> AcceptanceExecutionResult:
        """Run acceptance checks for one agent target."""

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


class QAApiTimeoutError(Exception):
    """Raised when a QA API operation times out."""


class QAApiRunFailedError(Exception):
    """Raised when a QA acceptance run fails."""


class QAApiListRunsFailedError(Exception):
    """Raised when listing QA acceptance runs fails."""


class QAApiRunDetailFailedError(Exception):
    """Raised when reading one QA acceptance run fails."""


class QAApiStatsFailedError(Exception):
    """Raised when reading QA statistics fails."""


class QAApiRunNotFoundError(Exception):
    """Raised when a QA acceptance run cannot be found."""


@dataclass(frozen=True, slots=True)
class QATriggerRunCommand:
    """Command for manually triggering a QA acceptance run."""

    agent_name: str
    level: str
    commit_sha: str | None
    files_changed: list[str]
    mr_iid: int | None
    gitlab_project_id: int | None
    requested_by: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class QAListRunsQuery:
    """Query for QA acceptance run history."""

    agent_name: str | None
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class QAStatsQuery:
    """Query for QA acceptance statistics."""

    agent_name: str | None
    days: int


class QAApiUseCase:
    """Application boundary used by QA HTTP routes."""

    def __init__(self, agent: QAApiAgentPort):
        self._agent = agent

    async def trigger_run(self, command: QATriggerRunCommand) -> dict[str, Any]:
        """Trigger a manual QA acceptance run and return API-ready data."""
        run_request = QARunRequest(
            agent_name=command.agent_name,
            level=command.level,
            commit_sha=command.commit_sha,
            files_changed=command.files_changed,
            mr_iid=command.mr_iid,
            gitlab_project_id=command.gitlab_project_id,
            trigger="manual",
            requested_by=command.requested_by,
            reason=command.reason,
        )
        try:
            result = await self._agent.run_acceptance(run_request)
        except asyncio.TimeoutError as exc:
            raise QAApiTimeoutError from exc
        except Exception as exc:
            raise QAApiRunFailedError(str(exc)) from exc

        return {
            "run_id": result.run_id,
            "status": _api_status_from_l0_gate(result.summary.l0_gate),
            "agent_name": command.agent_name,
            "level": command.level,
            "summary": result.summary,
            "duration_seconds": result.duration_seconds,
            "notification_summary": result.notification_summary,
        }

    async def list_runs(self, query: QAListRunsQuery) -> dict[str, Any]:
        """List QA acceptance run history as API-ready data."""
        try:
            runs_data = await self._agent.list_runs(
                agent_name=query.agent_name,
                limit=query.limit,
                offset=query.offset,
            )
        except Exception as exc:
            raise QAApiListRunsFailedError(str(exc)) from exc

        items = [
            {
                "run_id": row["id"],
                "agent_name": row["agent_name"],
                "commit_sha": row.get("commit_sha"),
                "mr_iid": row.get("mr_iid"),
                "trigger": row["trigger"],
                "l0_status": row["l0_status"],
                "l1_status": row["l1_status"],
                "total_checks": row["total_checks"],
                "duration_seconds": row["duration_seconds"],
                "created_at": row["created_at"],
            }
            for row in runs_data
        ]
        return {"total": len(items), "items": items}

    async def get_run_detail(self, run_id: str) -> dict[str, Any]:
        """Return one QA acceptance run as API-ready data."""
        try:
            run = await self._agent.get_run(run_id)
        except Exception as exc:
            raise QAApiRunDetailFailedError(str(exc)) from exc
        if not run:
            raise QAApiRunNotFoundError(run_id)

        return {
            "run_id": run["id"],
            "agent_name": run["agent_name"],
            "commit_sha": run.get("commit_sha"),
            "files_changed": run.get("files_changed", []),
            "trigger": run["trigger"],
            "level": run["level"],
            "summary": run["summary"],
            "findings": run.get("findings", []),
            "raw_report": run["raw_report"],
            "report_markdown": run.get("report_markdown"),
            "notification_summary": run.get("notification_summary", {}),
            "created_at": run["created_at"],
            "completed_at": run.get("completed_at"),
        }

    async def get_stats(self, query: QAStatsQuery) -> dict[str, Any]:
        """Return QA acceptance statistics as API-ready data."""
        try:
            stats = await self._agent.get_stats(
                agent_name=query.agent_name,
                days=query.days,
            )
        except Exception as exc:
            raise QAApiStatsFailedError(str(exc)) from exc

        return {
            "agent_name": stats.agent_name,
            "days": stats.days,
            "total_runs": stats.total_runs,
            "pass_runs": stats.pass_runs,
            "warn_runs": stats.warn_runs,
            "failed_runs": stats.failed_runs,
            "l0_fail_rate": stats.l0_fail_rate,
            "avg_duration_seconds": stats.avg_duration_seconds,
            "top_l0_failures": stats.top_l0_failures,
            "top_l1_warnings": stats.top_l1_warnings,
        }


def _api_status_from_l0_gate(l0_gate: str) -> str:
    return {
        "PASS": "passed",
        "FAIL": "failed",
        "WARN": "warn",
        "ERROR": "error",
    }.get(l0_gate, "error")
