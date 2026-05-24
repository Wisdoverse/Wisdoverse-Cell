"""Application use cases for QA acceptance run read models."""

from __future__ import annotations

from typing import Any

from shared.core.identifiers import AcceptanceRunId

from ..models.schemas import QARunStats
from .run_store import QAAcceptanceRunRecord, QAAcceptanceRunStore


class QARunQueryUseCase:
    """Read QA acceptance run projections outside the runtime service shell."""

    def __init__(self, *, run_store: QAAcceptanceRunStore) -> None:
        self._run_store = run_store

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        runs = await self._run_store.list_runs(
            agent_name=agent_name,
            limit=limit,
            offset=offset,
        )
        return [self._list_item(run) for run in runs]

    async def get_run(self, run_id: AcceptanceRunId) -> dict[str, Any] | None:
        run = await self._run_store.get_by_id(run_id)
        if run is None:
            return None
        return {
            "id": run.id,
            "run_id": run.id,
            "agent_name": run.agent_name,
            "commit_sha": run.commit_sha,
            "mr_iid": run.mr_iid,
            "trigger": run.trigger,
            "level": run.level,
            "files_changed": run.files_changed or [],
            "summary": {
                "l0_gate": run.l0_status,
                "l1_check": run.l1_status,
                "l2_report": run.l2_status,
                "total_checks": run.total_checks,
                "l0_failures": run.l0_failure_count,
                "l1_warnings": run.l1_warning_count,
            },
            "findings": run.raw_report.get("results", []) if run.raw_report else [],
            "raw_report": run.raw_report or {},
            "report_markdown": run.report_markdown,
            "notification_summary": run.notification_summary or {},
            "created_at": run.created_at.isoformat() if run.created_at else "",
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        return await self._run_store.get_stats(agent_name=agent_name, days=days)

    def _list_item(self, run: QAAcceptanceRunRecord) -> dict[str, Any]:
        return {
            "id": run.id,
            "run_id": run.id,
            "agent_name": run.agent_name,
            "commit_sha": run.commit_sha,
            "mr_iid": run.mr_iid,
            "trigger": run.trigger,
            "l0_status": run.l0_status,
            "l1_status": run.l1_status,
            "total_checks": run.total_checks,
            "duration_seconds": run.duration_seconds,
            "created_at": run.created_at.isoformat() if run.created_at else "",
        }
