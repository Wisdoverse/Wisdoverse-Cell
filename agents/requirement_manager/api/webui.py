"""WebUI compatibility API surface.

The Next.js operator UI still consumes a few legacy `/api/v1/*` endpoints while
the durable data model has moved into the control-plane and agent catalog
routers. Keep this adapter thin: it exposes backend-owned runtime state in the
shape the current UI expects, without duplicating business workflow logic.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from shared.config import settings
from shared.control_plane.agent_prompt_config import (
    AGENT_PROMPT_MAX_LENGTH,
    clean_system_prompt,
    clean_updated_by,
    ensure_prompt_config_target,
    get_or_default_prompt_config,
    prompt_config_to_dict,
)
from shared.control_plane.database import control_plane_db_manager
from shared.control_plane.models import AgentRunStatus, AuditEvent, CompanyContext, WorkItemStatus
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes

router = APIRouter(prefix="/api/v1", tags=["webui"])

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


class AgentPromptConfigRequest(BaseModel):
    system_prompt: str = Field(default="", max_length=AGENT_PROMPT_MAX_LENGTH)
    updated_by: str = Field(default="webui", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def _clean_system_prompt(cls, value: Any) -> str:
        return clean_system_prompt(value)

    @field_validator("updated_by", mode="before")
    @classmethod
    def _clean_updated_by(cls, value: Any) -> str:
        return clean_updated_by(value)


async def _ensure_company(repo: ControlPlaneRepository, company_id: str) -> None:
    if await repo.get_company(company_id) is not None:
        return
    await repo.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )


def _agent_runtime_status(
    *,
    agent_id: str,
    role_status: str | None,
    runs: list[Any],
    work_items: list[Any],
) -> dict[str, Any]:
    latest_run = max(runs, key=lambda run: run.started_at, default=None)
    failed_work_items = [
        work_item for work_item in work_items if work_item.status == WorkItemStatus.FAILED.value
    ]
    if latest_run is not None and latest_run.status in _RUNNING_RUN_STATUSES:
        status = "running"
    elif (latest_run is not None and latest_run.status in _FAILED_RUN_STATUSES) or failed_work_items:
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
        "pending_count": sum(1 for work_item in work_items if work_item.status in _OPEN_WORK_STATUSES),
        "error_count": sum(1 for run in runs if run.status in _FAILED_RUN_STATUSES) + len(failed_work_items),
        "uptime_seconds": 0,
        "last_active_at": last_active_at,
    }


@router.get("/agents")
async def list_agent_runtime_statuses(
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return runtime status summaries backed by control-plane records only."""

    resolved_company_id = settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        roles = await repo.list_agent_roles(
            company_id=resolved_company_id,
            search=search,
            limit=limit,
        )
        runs = await repo.list_agent_runs(company_id=resolved_company_id, limit=200)
        work_items = await repo.list_work_items(company_id=resolved_company_id, limit=500)

    rows = [
        _agent_runtime_status(
            agent_id=role.agent_id,
            role_status=role.status,
            runs=[run for run in runs if run.agent_id == role.agent_id],
            work_items=[
                work_item for work_item in work_items if work_item.owner_agent_id == role.agent_id
            ],
        )
        for role in roles
    ]
    if status:
        rows = [row for row in rows if row["status"] == status]
    return {"agents": rows[:limit], "total": len(rows)}


@router.get("/agents/{agent_id}/status")
async def get_agent_runtime_status(agent_id: str) -> dict[str, Any]:
    """Return one runtime status backed by control-plane records only."""

    resolved_company_id = settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        role = await repo.get_agent_role(
            company_id=resolved_company_id,
            agent_id=agent_id,
        )
        if role is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        runs = await repo.list_agent_runs(
            company_id=resolved_company_id,
            agent_id=agent_id,
            limit=200,
        )
        work_items = await repo.list_work_items(
            company_id=resolved_company_id,
            owner_agent_id=agent_id,
            limit=500,
        )
    return _agent_runtime_status(
        agent_id=agent_id,
        role_status=role.status,
        runs=runs,
        work_items=work_items,
    )


@router.get("/agents/{agent_id}/prompt-config")
async def get_agent_prompt_config(
    agent_id: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Return the persisted system-prompt override for an agent detail page."""

    resolved_company_id = company_id or settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        try:
            return await get_or_default_prompt_config(
                repo,
                company_id=resolved_company_id,
                agent_id=agent_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent_not_found") from exc


@router.put("/agents/{agent_id}/prompt-config")
async def update_agent_prompt_config(
    agent_id: str,
    body: AgentPromptConfigRequest,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Persist a system-prompt override used by deployed agent runtime code."""

    resolved_company_id = company_id or settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        await _ensure_company(repo, resolved_company_id)
        try:
            await ensure_prompt_config_target(
                repo,
                company_id=resolved_company_id,
                agent_id=agent_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent_not_found") from exc
        row = await repo.upsert_agent_prompt_config(
            company_id=resolved_company_id,
            agent_id=agent_id,
            system_prompt=body.system_prompt,
            updated_by=body.updated_by,
            metadata=body.metadata,
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=resolved_company_id,
                action=EventTypes.AGENT_PROMPT_CONFIG_UPDATED,
                target_type="agent_prompt_config",
                target_id=agent_id,
                actor_type="user",
                actor_id=body.updated_by,
                detail={
                    "agent_id": agent_id,
                    "prompt_length": len(body.system_prompt),
                    "metadata_keys": sorted(body.metadata.keys()),
                },
            )
        )
        return prompt_config_to_dict(
            row,
            company_id=resolved_company_id,
            agent_id=agent_id,
        )


@router.get("/approvals")
async def list_pending_approvals(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return root approval list alias backed by durable control-plane approvals."""

    resolved_company_id = settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        rows = await repo.list_approvals(
            company_id=resolved_company_id,
            status=status,
            limit=limit,
        )
    approvals = []
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        urgency = metadata.get("urgency")
        approvals.append(
            {
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
        )
    return {"approvals": approvals, "total": len(approvals)}


def _map_check_status(status: str) -> str:
    if status == "ok":
        return "ok"
    if status == "degraded":
        return "degraded"
    return "unhealthy"


@router.get("/health/ready")
async def webui_readiness(request: Request) -> dict[str, Any]:
    """Expose readiness in the shape used by the WebUI monitor page."""

    checks: dict[str, dict[str, str]] = {}
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None:
        runtime_checks = await runtime.health_check()
        for key, value in runtime_checks.items():
            name = key.removeprefix("infra-health.")
            if name in {"postgres", "redis", "milvus", "nats"}:
                checks[name] = {"status": _map_check_status(value.status)}

    for name in ("postgres", "redis", "milvus", "nats"):
        checks.setdefault(name, {"status": "ok" if name != "nats" else "degraded"})

    if any(check["status"] == "unhealthy" for check in checks.values()):
        status_value = "unhealthy"
    elif any(check["status"] == "degraded" for check in checks.values()):
        status_value = "degraded"
    else:
        status_value = "healthy"

    return {"status": status_value, "checks": checks}


async def _event_stream(request: Request) -> AsyncIterator[str]:
    yield ": connected\n\n"
    while not await request.is_disconnected():
        await asyncio.sleep(15)
        yield ": heartbeat\n\n"


@router.get("/events/stream")
async def stream_events(request: Request) -> StreamingResponse:
    """SSE endpoint used by the WebUI cache invalidation listener."""

    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
