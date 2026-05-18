"""PMAgent Decomposition API - REST endpoints for work-package decomposition."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from shared.api import (
    raise_pm_decomposition_forbidden,
    raise_pm_decomposition_not_found,
    raise_pm_decomposition_retry_failed,
    raise_pm_decomposition_unavailable,
)
from shared.utils.logger import get_logger

from ..core.api_use_cases import (
    PMApiDecompositionForbiddenError,
    PMApiDecompositionNotFoundError,
    PMApiDecompositionRetryFailedError,
    PMApiDecompositionUnavailableError,
    PMApiUseCase,
    PMDecompositionActionCommand,
)
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


def get_decomposition_api_use_case() -> PMApiUseCase:
    return PMApiUseCase(get_agent())


@router.post("/{wp_id}/approve", response_model=DecomposeActionResponse)
async def approve_decomposition(
    wp_id: int,
    body: ApproveRequest,
    pm_api: PMApiUseCase = Depends(get_decomposition_api_use_case),
):
    """Approve a pending decomposition and write results to OpenProject."""
    try:
        return DecomposeActionResponse.model_validate(
            await pm_api.approve_decomposition(
                PMDecompositionActionCommand(
                    wp_id=wp_id,
                    operator=body.operator,
                )
            )
        )
    except PMApiDecompositionUnavailableError:
        raise_pm_decomposition_unavailable()
    except PMApiDecompositionForbiddenError as exc:
        raise_pm_decomposition_forbidden(str(exc))


@router.post("/{wp_id}/reject", response_model=DecomposeActionResponse)
async def reject_decomposition(
    wp_id: int,
    body: RejectRequest,
    pm_api: PMApiUseCase = Depends(get_decomposition_api_use_case),
):
    """Reject a pending decomposition."""
    try:
        return DecomposeActionResponse.model_validate(
            await pm_api.reject_decomposition(
                PMDecompositionActionCommand(
                    wp_id=wp_id,
                    operator=body.operator,
                    reason=body.reason,
                )
            )
        )
    except PMApiDecompositionUnavailableError:
        raise_pm_decomposition_unavailable()
    except PMApiDecompositionForbiddenError as exc:
        raise_pm_decomposition_forbidden(str(exc))


@router.post("/{wp_id}/retry")
async def retry_decomposition(
    wp_id: int,
    pm_api: PMApiUseCase = Depends(get_decomposition_api_use_case),
):
    """Retry a failed decomposition."""
    try:
        result = await pm_api.retry_decomposition(wp_id)
    except PMApiDecompositionRetryFailedError as exc:
        raise_pm_decomposition_retry_failed(
            status_code=404,
            message=str(exc) or "Retry failed",
        )
    if not result:
        raise_pm_decomposition_not_found()
    return result


@router.get("/{wp_id}", response_model=DecomposeStatusResponse)
async def get_decomposition(
    wp_id: int,
    pm_api: PMApiUseCase = Depends(get_decomposition_api_use_case),
):
    """Get decomposition status for a work package."""
    try:
        return DecomposeStatusResponse.model_validate(
            await pm_api.get_decomposition(wp_id)
        )
    except PMApiDecompositionNotFoundError:
        raise_pm_decomposition_not_found()
