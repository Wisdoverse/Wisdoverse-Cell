"""AnalysisModule API - analysis report HTTP endpoints."""
from fastapi import APIRouter, Depends

from shared.api import (
    raise_analysis_daily_report_failed,
    raise_analysis_risk_check_failed,
    raise_analysis_weekly_report_failed,
)
from shared.utils.logger import get_logger

from ..core.api_use_cases import (
    AnalysisApiDailyReportFailedError,
    AnalysisApiRiskCheckFailedError,
    AnalysisApiUseCase,
    AnalysisApiWeeklyReportFailedError,
)
from ..service.agent import get_agent
from .schemas import DailyReportResponse, RiskCheckResponse, WeeklyReportResponse

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
logger = get_logger("analysis_module.api")


def get_analysis_api_use_case() -> AnalysisApiUseCase:
    return AnalysisApiUseCase(get_agent())


@router.post("/daily", response_model=DailyReportResponse)
async def generate_daily(
    analysis_api: AnalysisApiUseCase = Depends(get_analysis_api_use_case),
):
    """Manually trigger daily report generation."""
    try:
        return DailyReportResponse.model_validate(
            await analysis_api.generate_daily_report()
        )
    except AnalysisApiDailyReportFailedError as exc:
        logger.error("daily_report_api_error", error=str(exc))
        raise_analysis_daily_report_failed()


@router.post("/weekly", response_model=WeeklyReportResponse)
async def generate_weekly(
    analysis_api: AnalysisApiUseCase = Depends(get_analysis_api_use_case),
):
    """Manually trigger weekly report generation."""
    try:
        return WeeklyReportResponse.model_validate(
            await analysis_api.generate_weekly_report()
        )
    except AnalysisApiWeeklyReportFailedError as exc:
        logger.error("weekly_report_api_error", error=str(exc))
        raise_analysis_weekly_report_failed()


@router.get("/risks", response_model=RiskCheckResponse)
async def check_risks(
    analysis_api: AnalysisApiUseCase = Depends(get_analysis_api_use_case),
):
    """Check milestone risks."""
    try:
        return RiskCheckResponse.model_validate(await analysis_api.check_risks())
    except AnalysisApiRiskCheckFailedError as exc:
        logger.error("risk_check_api_error", error=str(exc))
        raise_analysis_risk_check_failed()
