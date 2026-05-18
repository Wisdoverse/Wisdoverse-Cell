"""
Messages API - message search and session lookup.

Endpoints:
- GET /api/messages/search - search messages with full-text support.
- GET /api/messages/session/{session_id} - get session details.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from agents.requirement_manager.api.dependencies import get_message_query_service
from agents.requirement_manager.core.message_queries import MessageQueryService
from shared.api import raise_session_not_found
from shared.utils.logger import get_logger

logger = get_logger("api.messages")

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


@router.get("/search")
async def search_messages(
    chat_id: Optional[str] = Query(None, description="Filter by chat ID"),
    keyword: Optional[str] = Query(None, description="Full-text search keyword"),
    sender_id: Optional[str] = Query(None, description="Filter by sender open_id"),
    start_time: Optional[datetime] = Query(None, description="Filter by start time"),
    end_time: Optional[datetime] = Query(None, description="Filter by end time"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    queries: MessageQueryService = Depends(get_message_query_service),
):
    """
    Search messages with optional filters and full-text search.

    Supports:
    - Full-text search by keyword (Chinese supported)
    - Filtering by chat_id, sender_id, time range
    - Pagination
    """
    result = await queries.search_messages(
        chat_id=chat_id,
        keyword=keyword,
        sender_id=sender_id,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    return {
        "messages": [_message_to_dict(message) for message in result.messages],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "total_pages": result.total_pages,
    }


@router.get("/session/{session_id}")
async def get_session_messages(
    session_id: str,
    queries: MessageQueryService = Depends(get_message_query_service),
):
    """
    Get all messages in a session.

    Returns messages ordered by sent_at ASC with session metadata.
    """
    result = await queries.get_session_messages(session_id)
    if result is None:
        raise_session_not_found()

    return {
        "session_id": result.session_id,
        "chat_id": result.chat_id,
        "messages": [_message_to_dict(message) for message in result.messages],
        "message_count": result.message_count,
        "started_at": result.started_at.isoformat() if result.started_at else None,
        "ended_at": result.ended_at.isoformat() if result.ended_at else None,
        "extracted": result.extracted,
        "requirement_ids": result.requirement_ids,
    }


def _message_to_dict(message) -> dict:
    """Convert message read model to dict for API response."""
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "message_type": message.message_type,
        "content": message.content,
        "session_id": message.session_id,
        "extracted": message.extracted,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }
