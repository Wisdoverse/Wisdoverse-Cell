"""AnalysisModule API - analysis report HTTP endpoints."""
from fastapi import APIRouter, HTTPException

from shared.utils.logger import get_logger

from ..service.agent import get_agent
from .schemas import DailyReportResponse, RiskCheckResponse, WeeklyReportResponse

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
logger = get_logger("analysis_module.api")


@router.post("/daily", response_model=DailyReportResponse)
async def generate_daily():
    """Manually trigger daily report generation."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "daily_report"})
        return DailyReportResponse(**result)
    except Exception as e:
        logger.error("daily_report_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="Daily report generation failed. Please retry later.")


@router.post("/weekly", response_model=WeeklyReportResponse)
async def generate_weekly():
    """Manually trigger weekly report generation."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "weekly_report"})
        return WeeklyReportResponse(**result)
    except Exception as e:
        logger.error("weekly_report_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="Weekly report generation failed. Please retry later.")


@router.get("/risks", response_model=RiskCheckResponse)
async def check_risks():
    """Check milestone risks."""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "check_milestones"})
        risks = result.get("risks", [])
        return RiskCheckResponse(total=len(risks), risks=risks)
    except Exception as e:
        logger.error("risk_check_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="Risk check failed. Please retry later.")
