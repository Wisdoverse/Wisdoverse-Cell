"""PMAgent API - PM alert HTTP endpoints."""

from fastapi import APIRouter, HTTPException

from shared.utils.logger import get_logger

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


def _raise_agent_error(
    *,
    status_code: int,
    public_detail: str,
    log_event: str,
    result: dict,
) -> None:
    logger.warning(log_event, error=str(result.get("error", "")))
    raise HTTPException(status_code=status_code, detail=public_detail)


@router.get("/config", response_model=PMConfigResponse)
async def get_config():
    """Get PM configuration."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "config"})
        return PMConfigResponse(**result)
    except Exception as e:
        logger.error("config_api_error", error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to get PM configuration. Please retry later."
        )


@router.post("/config/refresh", response_model=ConfigRefreshResponse)
async def refresh_config():
    """Refresh PM configuration."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "refresh_config"})
        return ConfigRefreshResponse(**result)
    except Exception as e:
        logger.error("config_refresh_api_error", error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to refresh PM configuration. Please retry later."
        )


@router.get("/alerts", response_model=AlertListResponse)
async def get_alerts():
    """Get current alerts."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "alerts"})
        alerts = result.get("alerts", [])
        return AlertListResponse(total=len(alerts), alerts=alerts)
    except Exception as e:
        logger.error("alerts_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get PM alerts. Please retry later.")


@router.post("/report/daily")
async def trigger_daily_report():
    """Manually trigger a daily report."""
    agent = get_agent()
    result = await agent.handle_request({"action": "daily_report"})
    if result.get("error"):
        _raise_agent_error(
            status_code=500,
            public_detail="Failed to generate daily report. Please retry later.",
            log_event="daily_report_api_result_error",
            result=result,
        )
    return result


@router.post("/report/weekly")
async def trigger_weekly_report():
    """Manually trigger a weekly report."""
    agent = get_agent()
    result = await agent.handle_request({"action": "weekly_report"})
    if result.get("error"):
        _raise_agent_error(
            status_code=500,
            public_detail="Failed to generate weekly report. Please retry later.",
            log_event="weekly_report_api_result_error",
            result=result,
        )
    return result


@router.post("/decompose/{wp_id}/retry")
async def retry_decomposition(wp_id: int):
    """Retry a failed decomposition."""
    agent = get_agent()
    result = await agent.handle_request({"action": "retry_decompose", "wp_id": wp_id})
    if result.get("error"):
        _raise_agent_error(
            status_code=400,
            public_detail="Failed to retry decomposition. Please retry later.",
            log_event="retry_decompose_api_result_error",
            result=result,
        )
    return result


@router.get("/decompose/{wp_id}", response_model=DecomposeStatusResponse)
async def get_decomposition(wp_id: int):
    """Query decomposition status."""
    agent = get_agent()
    result = await agent.handle_request({"action": "get_decompose", "wp_id": wp_id})
    if not result:
        raise HTTPException(status_code=404, detail="Record not found")
    return DecomposeStatusResponse(**result)


@router.post("/decompose/{wp_id}/approve", response_model=DecomposeActionResponse)
async def approve_decomposition(wp_id: int, body: DecomposeActionRequest):
    """Approve decomposition and write to OpenProject."""
    agent = get_agent()
    result = await agent.approve_decomposition(wp_id, approved_by=body.operator)
    if result is None:
        raise HTTPException(status_code=400, detail="Record not found or status is not pending")
    if result.get("error"):
        raise HTTPException(status_code=403, detail=result["error"])
    return DecomposeActionResponse(
        success=True,
        wp_id=wp_id,
        action="approve",
        message=f"Written to OP: {result.get('story_count', 0)} US, {result.get('task_count', 0)} Task",
        subject=result.get("subject", ""),
        story_count=result.get("story_count", 0),
        task_count=result.get("task_count", 0),
    )


@router.post("/decompose/{wp_id}/reject", response_model=DecomposeActionResponse)
async def reject_decomposition(wp_id: int, body: DecomposeActionRequest):
    """Reject decomposition."""
    agent = get_agent()
    result = await agent.reject_decomposition(
        wp_id,
        rejected_by=body.operator,
        reason=body.reason,
    )
    if result is None:
        raise HTTPException(status_code=400, detail="Record not found or status is not pending")
    if result.get("error"):
        raise HTTPException(status_code=403, detail=result["error"])
    return DecomposeActionResponse(
        success=True,
        wp_id=wp_id,
        action="reject",
        message="Rejected",
        subject=result.get("subject", ""),
    )
