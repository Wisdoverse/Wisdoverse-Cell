"""Daily-progress read endpoints owned by the chat-agent runtime."""

from datetime import date

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/daily-progress", tags=["daily-progress"])


@router.get("")
async def get_daily_progress(
    request: Request,
    target_date: date | None = Query(
        default=None,
        description="Target date; defaults to today",
    ),
    user_id: str = Query(default="", description="Filter by user identifier"),
    days: int = Query(default=1, description="Date range in days"),
) -> dict:
    """Return daily-progress rows through the chat-agent request boundary."""
    return await request.app.state.runtime.agent.handle_request(
        {
            "action": "list_daily_progress",
            "target_date": target_date,
            "user_id": user_id,
            "days": days,
        }
    )
