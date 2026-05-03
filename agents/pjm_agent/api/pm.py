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


@router.get("/config", response_model=PMConfigResponse)
async def get_config():
    """Get PM configuration."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "config"})
        return PMConfigResponse(**result)
    except Exception as e:
        logger.error("config_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="获取配置失败，请稍后重试")


@router.post("/config/refresh", response_model=ConfigRefreshResponse)
async def refresh_config():
    """Refresh PM configuration."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "refresh_config"})
        return ConfigRefreshResponse(**result)
    except Exception as e:
        logger.error("config_refresh_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="刷新配置失败，请稍后重试")


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
        raise HTTPException(status_code=500, detail="获取预警失败，请稍后重试")


@router.post("/report/daily")
async def trigger_daily_report():
    """Manually trigger a daily report."""
    agent = get_agent()
    result = await agent.handle_request({"action": "daily_report"})
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/report/weekly")
async def trigger_weekly_report():
    """Manually trigger a weekly report."""
    agent = get_agent()
    result = await agent.handle_request({"action": "weekly_report"})
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/decompose/{wp_id}/retry")
async def retry_decomposition(wp_id: int):
    """Retry a failed decomposition."""
    agent = get_agent()
    result = await agent.handle_request({"action": "retry_decompose", "wp_id": wp_id})
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/decompose/{wp_id}", response_model=DecomposeStatusResponse)
async def get_decomposition(wp_id: int):
    """Query decomposition status."""
    agent = get_agent()
    result = await agent.handle_request({"action": "get_decompose", "wp_id": wp_id})
    if not result:
        raise HTTPException(status_code=404, detail="记录不存在")
    return DecomposeStatusResponse(**result)


@router.post("/decompose/{wp_id}/approve", response_model=DecomposeActionResponse)
async def approve_decomposition(wp_id: int, body: DecomposeActionRequest):
    """Approve decomposition and write to OpenProject."""
    agent = get_agent()
    result = await agent.approve_decomposition(wp_id, approved_by=body.operator or "api")
    if result is None:
        raise HTTPException(status_code=400, detail="记录不存在或状态不是 pending")
    return DecomposeActionResponse(
        success=True,
        wp_id=wp_id,
        action="approve",
        message=f"已写入 OP: {result.get('story_count', 0)} US, {result.get('task_count', 0)} Task",
        subject=result.get("subject", ""),
        story_count=result.get("story_count", 0),
        task_count=result.get("task_count", 0),
    )


@router.post("/decompose/{wp_id}/reject", response_model=DecomposeActionResponse)
async def reject_decomposition(wp_id: int, body: DecomposeActionRequest):
    """Reject decomposition."""
    agent = get_agent()
    result = await agent.reject_decomposition(wp_id, rejected_by=body.operator or "api")
    if result is None:
        raise HTTPException(status_code=400, detail="记录不存在或状态不是 pending")
    return DecomposeActionResponse(
        success=True,
        wp_id=wp_id,
        action="reject",
        message="已拒绝",
        subject=result.get("subject", ""),
    )
