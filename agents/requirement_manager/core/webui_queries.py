"""Application query use cases for WebUI compatibility read models."""

from typing import Any

from shared.control_plane.models import AgentRunStatus, WorkItemStatus

from .webui_ports import WebUIControlPlaneQueryStore

_RUNNING_RUN_STATUSES = {AgentRunStatus.PENDING.value, AgentRunStatus.RUNNING.value}
_FAILED_RUN_STATUSES = {AgentRunStatus.FAILED.value, AgentRunStatus.TIMED_OUT.value}
_OPEN_WORK_STATUSES = {
    WorkItemStatus.QUEUED.value,
    WorkItemStatus.READY.value,
    WorkItemStatus.RUNNING.value,
    WorkItemStatus.BLOCKED.value,
    WorkItemStatus.AWAITING_APPROVAL.value,
}
_STOPPED_ROLE_STATUSES = {"paused", "stopped", "disabled", "inactive", "retired"}


class WebUIQueryService:
    """Application use case for WebUI compatibility queries."""

    def __init__(self, *, store: WebUIControlPlaneQueryStore, company_id: str):
        self._store = store
        self._company_id = company_id

    async def list_agent_runtime_statuses(
        self,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        roles = await self._store.list_agent_roles(
            company_id=self._company_id,
            search=search,
            limit=limit,
        )
        runs = await self._store.list_agent_runs(
            company_id=self._company_id,
            limit=200,
        )
        work_items = await self._store.list_work_items(
            company_id=self._company_id,
            limit=500,
        )

        rows = [
            _agent_runtime_status(
                agent_id=role.agent_id,
                role_status=role.status,
                runs=[run for run in runs if run.agent_id == role.agent_id],
                work_items=[
                    work_item
                    for work_item in work_items
                    if work_item.owner_agent_id == role.agent_id
                ],
            )
            for role in roles
        ]
        if status:
            rows = [row for row in rows if row["status"] == status]
        return {"agents": rows[:limit], "total": len(rows)}

    async def get_agent_runtime_status(self, agent_id: str) -> dict[str, Any] | None:
        role = await self._store.get_agent_role(
            company_id=self._company_id,
            agent_id=agent_id,
        )
        if role is None:
            return None
        runs = await self._store.list_agent_runs(
            company_id=self._company_id,
            agent_id=agent_id,
            limit=200,
        )
        work_items = await self._store.list_work_items(
            company_id=self._company_id,
            owner_agent_id=agent_id,
            limit=500,
        )
        return _agent_runtime_status(
            agent_id=agent_id,
            role_status=role.status,
            runs=runs,
            work_items=work_items,
        )

    async def list_pending_approvals(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        rows = await self._store.list_approvals(
            company_id=self._company_id,
            status=status,
            limit=limit,
        )
        approvals = [_approval_to_dict(row) for row in rows]
        return {"approvals": approvals, "total": len(approvals)}


def _agent_runtime_status(
    *,
    agent_id: str,
    role_status: str | None,
    runs: list[Any],
    work_items: list[Any],
) -> dict[str, Any]:
    latest_run = max(runs, key=lambda run: run.started_at, default=None)
    failed_work_items = [
        work_item
        for work_item in work_items
        if work_item.status == WorkItemStatus.FAILED.value
    ]
    if latest_run is not None and latest_run.status in _RUNNING_RUN_STATUSES:
        status = "running"
    elif (
        latest_run is not None and latest_run.status in _FAILED_RUN_STATUSES
    ) or failed_work_items:
        status = "error"
    elif role_status in _STOPPED_ROLE_STATUSES:
        status = "stopped"
    else:
        status = "idle"

    last_active_at = None
    timestamps = [run.completed_at or run.started_at for run in runs]
    timestamps.extend(work_item.updated_at for work_item in work_items)
    if timestamps:
        last_active_at = max(timestamps).isoformat()

    return {
        "agent_id": agent_id,
        "status": status,
        "health": 100 if status == "running" else 0 if status in {"error", "stopped"} else 50,
        "task_count": len(runs),
        "pending_count": sum(
            1 for work_item in work_items if work_item.status in _OPEN_WORK_STATUSES
        ),
        "error_count": sum(1 for run in runs if run.status in _FAILED_RUN_STATUSES)
        + len(failed_work_items),
        "uptime_seconds": 0,
        "last_active_at": last_active_at,
    }


def _approval_to_dict(row: object) -> dict[str, Any]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    urgency = metadata.get("urgency")
    return {
        "id": row.approval_id,
        "source_agent_id": row.source_agent_id,
        "approval_type": row.category,
        "title": row.proposed_action,
        "summary": row.reason or row.risk,
        "context_link": row.artifact_links[0] if row.artifact_links else None,
        "urgency": urgency if urgency in {"urgent", "normal", "low"} else "normal",
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolved_by": row.resolved_by,
    }
