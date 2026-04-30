"""AnalysisAgent API - 分析报告 HTTP 端点"""
from fastapi import APIRouter, HTTPException

from shared.utils.logger import get_logger

from ..service.agent import get_agent
from .schemas import DailyReportResponse, RiskCheckResponse, WeeklyReportResponse

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
logger = get_logger("analysis_agent.api")


@router.post("/daily", response_model=DailyReportResponse)
async def generate_daily():
    """手动触发日报生成"""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "daily_report"})
        return DailyReportResponse(**result)
    except Exception as e:
        logger.error("daily_report_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="日报生成失败，请稍后重试")


@router.post("/weekly", response_model=WeeklyReportResponse)
async def generate_weekly():
    """手动触发周报生成"""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "weekly_report"})
        return WeeklyReportResponse(**result)
    except Exception as e:
        logger.error("weekly_report_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="周报生成失败，请稍后重试")


@router.get("/risks", response_model=RiskCheckResponse)
async def check_risks():
    """检查里程碑风险"""
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "check_milestones"})
        risks = result.get("risks", [])
        return RiskCheckResponse(total=len(risks), risks=risks)
    except Exception as e:
        logger.error("risk_check_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="风险检查失败，请稍后重试")
