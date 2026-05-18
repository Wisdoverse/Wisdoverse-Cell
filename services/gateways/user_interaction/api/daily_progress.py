"""Daily progress API — PJM Agent reads this for report generation."""
from datetime import date

from fastapi import APIRouter, Depends, Query

from ..core.daily_progress_queries import DailyProgressQueryService
from .dependencies import get_daily_progress_query_service

router = APIRouter(prefix="/api/daily-progress", tags=["daily-progress"])


@router.get("")
async def get_daily_progress(
    target_date: date = Query(default=None, description="Target date; defaults to today"),
    user_id: str = Query(default="", description="Filter by user identifier"),
    days: int = Query(default=1, description="Date range in days"),
    queries: DailyProgressQueryService = Depends(get_daily_progress_query_service),
):
    """Get daily progress entries for reporting."""
    return await queries.list_progress_response(
        target_date=target_date,
        user_id=user_id,
        days=days,
    )
