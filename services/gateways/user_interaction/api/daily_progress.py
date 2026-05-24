"""Compatibility daily-progress proxy to the chat-agent API."""

from datetime import date

from fastapi import APIRouter, Query

from ..adapters.chat_agent_client import get_chat_agent_client

router = APIRouter(prefix="/api/daily-progress", tags=["daily-progress"])


@router.get("")
async def get_daily_progress(
    target_date: date | None = Query(
        default=None,
        description="Target date; defaults to today",
    ),
    user_id: str = Query(default="", description="Filter by user identifier"),
    days: int = Query(default=1, description="Date range in days"),
) -> dict:
    """Proxy daily-progress reads to the chat-agent service boundary."""
    return await get_chat_agent_client().list_daily_progress(
        target_date=target_date,
        user_id=user_id,
        days=days,
    )
