"""WebUI compatibility API surface.

The Next.js operator UI still consumes a few legacy `/api/v1/*` endpoints while
the durable data model has moved into the control-plane and agent catalog
routers. Keep this adapter thin: it exposes backend-owned runtime state in the
shape the current UI expects, without duplicating business workflow logic.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from shared.api import raise_agent_not_found
from shared.config import settings
from shared.control_plane.agent_prompt_config import (
    AGENT_PROMPT_MAX_LENGTH,
    clean_system_prompt,
    clean_updated_by,
)
from shared.control_plane.database import control_plane_db_manager

from ..core.webui_prompt_config import WebUIPromptConfigUseCase
from ..core.webui_queries import WebUIQueryService
from ..db.webui_control_plane_store import SqlAlchemyWebUIControlPlaneStore

router = APIRouter(prefix="/api/v1", tags=["webui"])


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


def get_webui_query_service() -> WebUIQueryService:
    store = SqlAlchemyWebUIControlPlaneStore(control_plane_db_manager)
    return WebUIQueryService(
        store=store,
        company_id=settings.control_plane_company_id,
    )


def get_webui_prompt_config_use_case() -> WebUIPromptConfigUseCase:
    store = SqlAlchemyWebUIControlPlaneStore(control_plane_db_manager)
    return WebUIPromptConfigUseCase(
        store=store,
        default_company_id=settings.control_plane_company_id,
    )


@router.get("/agents")
async def list_agent_runtime_statuses(
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    queries: WebUIQueryService = Depends(get_webui_query_service),
) -> dict[str, Any]:
    """Return runtime status summaries backed by control-plane records only."""
    return await queries.list_agent_runtime_statuses(
        status=status,
        search=search,
        limit=limit,
    )


@router.get("/agents/{agent_id}/status")
async def get_agent_runtime_status(
    agent_id: str,
    queries: WebUIQueryService = Depends(get_webui_query_service),
) -> dict[str, Any]:
    """Return one runtime status backed by control-plane records only."""
    result = await queries.get_agent_runtime_status(agent_id)
    if result is None:
        raise_agent_not_found()
    return result


@router.get("/agents/{agent_id}/prompt-config")
async def get_agent_prompt_config(
    agent_id: str,
    company_id: str | None = None,
    prompt_configs: WebUIPromptConfigUseCase = Depends(
        get_webui_prompt_config_use_case
    ),
) -> dict[str, Any]:
    """Return the persisted system-prompt override for an agent detail page."""

    result = await prompt_configs.get_prompt_config(
        agent_id=agent_id,
        company_id=company_id,
    )
    if result is None:
        raise_agent_not_found()
    return result


@router.put("/agents/{agent_id}/prompt-config")
async def update_agent_prompt_config(
    agent_id: str,
    body: AgentPromptConfigRequest,
    company_id: str | None = None,
    prompt_configs: WebUIPromptConfigUseCase = Depends(
        get_webui_prompt_config_use_case
    ),
) -> dict[str, Any]:
    """Persist a system-prompt override used by deployed agent runtime code."""

    result = await prompt_configs.update_prompt_config(
        agent_id=agent_id,
        system_prompt=body.system_prompt,
        updated_by=body.updated_by,
        metadata=body.metadata,
        company_id=company_id,
    )
    if result is None:
        raise_agent_not_found()
    return result


@router.get("/approvals")
async def list_pending_approvals(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    queries: WebUIQueryService = Depends(get_webui_query_service),
) -> dict[str, Any]:
    """Return root approval list alias backed by durable control-plane approvals."""
    return await queries.list_pending_approvals(status=status, limit=limit)


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
