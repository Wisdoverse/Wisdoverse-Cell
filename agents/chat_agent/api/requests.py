"""Internal request endpoint owned by the chat-agent runtime."""

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/chat-agent", tags=["chat-agent"])


@router.post("/requests")
async def handle_chat_agent_request(
    payload: dict[str, Any],
    request: Request,
) -> dict:
    """Execute a normalized chat-agent request behind the service boundary."""
    return await request.app.state.runtime.agent.handle_request(payload)
