"""PMAgent API - PM alert HTTP endpoints."""

from fastapi import APIRouter, Depends

from shared.api import (
    ApiErrorCode,
    raise_api_error,
    raise_pm_alerts_failed,
    raise_pm_config_failed,
    raise_pm_config_refresh_failed,
    raise_pm_decomposition_forbidden,
    raise_pm_decomposition_not_found,
    raise_pm_decomposition_retry_failed,
    raise_pm_decomposition_unavailable,
)
from shared.utils.logger import get_logger

from ..core.api_use_cases import (
    PMApiAlertsFailedError,
    PMApiConfigFailedError,
    PMApiConfigRefreshFailedError,
    PMApiDecompositionForbiddenError,
    PMApiDecompositionNotFoundError,
    PMApiDecompositionRetryFailedError,
    PMApiDecompositionUnavailableError,
    PMApiReportFailedError,
    PMApiUseCase,
    PMDecompositionActionCommand,
)
from ..service.agent import get_agent
from .schemas import (
    AlertListResponse,
    ConfigRefreshResponse,
    DecomposeActionRequest,
    DecomposeActionResponse,
    DecomposeStatusResponse,
    PMConfigResponse,
)

router = APIRouter(prefix="/api/v1/pm", tags=["pm"])
logger = get_logger("pjm_agent.api")


def get_pm_api_use_case() -> PMApiUseCase:
    return PMApiUseCase(get_agent())


def _raise_agent_error(
    *,
    status_code: int,
    public_detail: str,
    log_event: str,
    result: dict,
    code: ApiErrorCode,
) -> None:
    logger.warning(log_event, error=str(result.get("error", "")))
    raise_api_error(status_code=status_code, code=code, message=public_detail)


@router.get("/config", response_model=PMConfigResponse)
async def get_config(pm_api: PMApiUseCase = Depends(get_pm_api_use_case)):
    """Get PM configuration."""
    try:
        return PMConfigResponse.model_validate(await pm_api.get_config())
    except PMApiConfigFailedError as exc:
        logger.error("config_api_error", error=str(exc))
        raise_pm_config_failed()


@router.post("/config/refresh", response_model=ConfigRefreshResponse)
async def refresh_config(pm_api: PMApiUseCase = Depends(get_pm_api_use_case)):
    """Refresh PM configuration."""
    try:
        return ConfigRefreshResponse.model_validate(await pm_api.refresh_config())
    except PMApiConfigRefreshFailedError as exc:
        logger.error("config_refresh_api_error", error=str(exc))
        raise_pm_config_refresh_failed()


@router.get("/alerts", response_model=AlertListResponse)
async def get_alerts(pm_api: PMApiUseCase = Depends(get_pm_api_use_case)):
    """Get current alerts."""
    try:
        return AlertListResponse.model_validate(await pm_api.get_alerts())
    except PMApiAlertsFailedError as exc:
        logger.error("alerts_api_error", error=str(exc))
        raise_pm_alerts_failed()


@router.post("/report/daily")
async def trigger_daily_report(pm_api: PMApiUseCase = Depends(get_pm_api_use_case)):
    """Manually trigger a daily report."""
    try:
        return await pm_api.trigger_daily_report()
    except PMApiReportFailedError as exc:
        _raise_agent_error(
            status_code=500,
            public_detail="Failed to generate daily report. Please retry later.",
            log_event="daily_report_api_result_error",
            result={"error": str(exc)},
            code=ApiErrorCode.PM_DAILY_REPORT_FAILED,
        )


@router.post("/report/weekly")
async def trigger_weekly_report(pm_api: PMApiUseCase = Depends(get_pm_api_use_case)):
    """Manually trigger a weekly report."""
    try:
        return await pm_api.trigger_weekly_report()
    except PMApiReportFailedError as exc:
        _raise_agent_error(
            status_code=500,
            public_detail="Failed to generate weekly report. Please retry later.",
            log_event="weekly_report_api_result_error",
            result={"error": str(exc)},
            code=ApiErrorCode.PM_WEEKLY_REPORT_FAILED,
        )


@router.post("/decompose/{wp_id}/retry")
async def retry_decomposition(
    wp_id: int,
    pm_api: PMApiUseCase = Depends(get_pm_api_use_case),
):
    """Retry a failed decomposition."""
    try:
        return await pm_api.retry_decomposition(wp_id)
    except PMApiDecompositionRetryFailedError as exc:
        logger.warning("retry_decompose_api_result_error", error=str(exc))
        raise_pm_decomposition_retry_failed()


@router.get("/decompose/{wp_id}", response_model=DecomposeStatusResponse)
async def get_decomposition(
    wp_id: int,
    pm_api: PMApiUseCase = Depends(get_pm_api_use_case),
):
    """Query decomposition status."""
    try:
        return DecomposeStatusResponse.model_validate(
            await pm_api.get_decomposition(wp_id)
        )
    except PMApiDecompositionNotFoundError:
        raise_pm_decomposition_not_found()


@router.post("/decompose/{wp_id}/approve", response_model=DecomposeActionResponse)
async def approve_decomposition(
    wp_id: int,
    body: DecomposeActionRequest,
    pm_api: PMApiUseCase = Depends(get_pm_api_use_case),
):
    """Approve decomposition and write to OpenProject."""
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
        raise_pm_decomposition_unavailable(status_code=400)
    except PMApiDecompositionForbiddenError as exc:
        raise_pm_decomposition_forbidden(str(exc))


@router.post("/decompose/{wp_id}/reject", response_model=DecomposeActionResponse)
async def reject_decomposition(
    wp_id: int,
    body: DecomposeActionRequest,
    pm_api: PMApiUseCase = Depends(get_pm_api_use_case),
):
    """Reject decomposition."""
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
        raise_pm_decomposition_unavailable(status_code=400)
    except PMApiDecompositionForbiddenError as exc:
        raise_pm_decomposition_forbidden(str(exc))
