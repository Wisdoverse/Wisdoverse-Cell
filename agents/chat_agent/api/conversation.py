"""Conversation read endpoints owned by the chat-agent runtime."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/chat-agent", tags=["chat-agent"])


@router.get("/conversation/{user_id}")
async def get_conversation_history(user_id: str, request: Request) -> dict:
    """Return persisted conversation history through the chat-agent boundary."""
    return await request.app.state.runtime.agent.handle_request(
        {
            "action": "get_conversation_history",
            "user_id": user_id,
        }
    )
