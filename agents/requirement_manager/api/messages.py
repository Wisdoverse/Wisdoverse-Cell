"""
Messages API - message search and session lookup.

Endpoints:
- GET /api/messages/search - search messages with full-text support.
- GET /api/messages/session/{session_id} - get session details.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agents.requirement_manager.db.database import get_db
from agents.requirement_manager.db.repository import MessageRepository
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
    db: AsyncSession = Depends(get_db),
):
    """
    Search messages with optional filters and full-text search.

    Supports:
    - Full-text search by keyword (Chinese supported)
    - Filtering by chat_id, sender_id, time range
    - Pagination
    """
    repo = MessageRepository(db)
    messages, total = await repo.search(
        keyword=keyword,
        chat_id=chat_id,
        sender_id=sender_id,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    return {
        "messages": [_message_to_dict(m) for m in messages],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/session/{session_id}")
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all messages in a session.

    Returns messages ordered by sent_at ASC with session metadata.
    """
    repo = MessageRepository(db)
    messages = await repo.get_by_session(session_id)

    if not messages:
        raise HTTPException(status_code=404, detail="Session not found or has no messages")

    # Get session metadata
    first_msg = messages[0]
    last_msg = messages[-1]

    # Check if any requirements were extracted from this session
    requirement_ids = set()
    for msg in messages:
        if msg.requirement_ids:
            requirement_ids.update(msg.requirement_ids)

    return {
        "session_id": session_id,
        "chat_id": first_msg.chat_id,
        "messages": [_message_to_dict(m) for m in messages],
        "message_count": len(messages),
        "started_at": first_msg.sent_at.isoformat() if first_msg.sent_at else None,
        "ended_at": last_msg.sent_at.isoformat() if last_msg.sent_at else None,
        "extracted": any(m.extracted for m in messages),
        "requirement_ids": list(requirement_ids),
    }


def _message_to_dict(message) -> dict:
    """Convert ChatMessage model to dict for API response"""
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
