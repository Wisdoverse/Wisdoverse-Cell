"""Daily progress API — PJM Agent reads this for report generation."""
from datetime import date, timedelta

from fastapi import APIRouter, Query

from ..db.database import db_manager
from ..db.repository import DailyProgressRepository

router = APIRouter(prefix="/api/daily-progress", tags=["daily-progress"])


@router.get("")
async def get_daily_progress(
    target_date: date = Query(default=None, description="Target date; defaults to today"),
    user_id: str = Query(default="", description="Filter by user identifier"),
    days: int = Query(default=1, description="Date range in days"),
):
    """Get daily progress entries for reporting."""
    end = target_date or date.today()
    start = end - timedelta(days=days - 1)

    async with db_manager.session() as session:
        repo = DailyProgressRepository(session)
        entries = await repo.get_by_date_range(start, end, user_id=user_id)

    results = []
    for e in entries:
        results.append({
            "id": e.id,
            "user_id": e.user_id,
            "user_name": e.user_name,
            "date": e.date.isoformat(),
            "task_record_id": e.task_record_id,
            "task_title": e.task_title,
            "status": e.status,
            "note": e.note or "",
            "raw_reply": e.raw_reply or "",
        })

    return {"entries": results, "total": len(results)}
