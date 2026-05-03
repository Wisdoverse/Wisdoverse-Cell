"""PMAgent Decomposition API - REST endpoints for work-package decomposition."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from shared.utils.logger import get_logger

from ..service.agent import get_agent

logger = get_logger("pjm_agent.api.decomposition")

router = APIRouter(prefix="/api/v1/pm/decompose", tags=["decomposition"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    model_config = ConfigDict(strict=False)
    operator: str = ""


class RejectRequest(BaseModel):
    model_config = ConfigDict(strict=False)
    operator: str = ""
    reason: str = ""


class DecomposeActionResponse(BaseModel):
    model_config = ConfigDict(strict=False)
    success: bool
    wp_id: int
    action: str
    message: str = ""
    subject: str = ""
    story_count: int = 0
    task_count: int = 0


class DecomposeStatusResponse(BaseModel):
    model_config = ConfigDict(strict=False)
    wp_id: int
    project_id: int
    status: str
    assignee_id: int | None = None
    decompose_result: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
    approved_by: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{wp_id}/approve", response_model=DecomposeActionResponse)
async def approve_decomposition(wp_id: int, body: ApproveRequest):
    """Approve a pending decomposition and write results to OpenProject."""
    agent = get_agent()
    result = await agent.approve_decomposition(wp_id, approved_by=body.operator or "api")
    if result is None:
        raise HTTPException(status_code=404, detail="Record not found or status is not pending")
    return DecomposeActionResponse(
        success=True,
        wp_id=wp_id,
        action="approve",
        message=(
            f"Written to OP: {result.get('story_count', 0)} US, "
            f"{result.get('task_count', 0)} Task"
        ),
        subject=result.get("subject", ""),
        story_count=result.get("story_count", 0),
        task_count=result.get("task_count", 0),
    )


@router.post("/{wp_id}/reject", response_model=DecomposeActionResponse)
async def reject_decomposition(wp_id: int, body: RejectRequest):
    """Reject a pending decomposition."""
    agent = get_agent()
    result = await agent.reject_decomposition(
        wp_id,
        rejected_by=body.operator or "api",
        reason=body.reason,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Record not found or status is not pending")
    return DecomposeActionResponse(
        success=True,
        wp_id=wp_id,
        action="reject",
        message="Rejected",
        subject=result.get("subject", ""),
    )


@router.post("/{wp_id}/retry")
async def retry_decomposition(wp_id: int):
    """Retry a failed decomposition."""
    agent = get_agent()
    result = await agent._retry_decompose(wp_id)
    if not result or result.get("error"):
        detail = result.get("error", "Retry failed") if result else "Record not found"
        raise HTTPException(status_code=404, detail=detail)
    return result


@router.get("/{wp_id}", response_model=DecomposeStatusResponse)
async def get_decomposition(wp_id: int):
    """Get decomposition status for a work package."""
    agent = get_agent()
    result = await agent._get_decompose(wp_id)
    if not result:
        raise HTTPException(status_code=404, detail="Record not found")
    return DecomposeStatusResponse(**result)
