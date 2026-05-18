"""Application use cases for user-interaction agent requests."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from shared.core import unknown_action_error
from shared.utils.logger import get_logger

from .chat_ports import ChatHistoryStore

logger = get_logger("chat_agent.requests")

AsyncCommand = Callable[[], Awaitable[Any]]


class UserInteractionChatPort(Protocol):
    """Chat operations required by user-interaction request handling."""

    async def chat(self, *, message: str, user_id: str) -> str:
        """Run a plain chat request."""

    async def chat_with_user_assistant(
        self,
        *,
        message: str,
        user_id: str,
        user_name: str,
        context: dict[str, Any],
    ) -> str:
        """Run the Feishu user assistant chat request."""

    async def clear_history(self, user_id: str) -> None:
        """Clear the conversation history for a user."""


class UserInteractionRequestUseCase:
    """Dispatch and execute user-interaction agent request actions."""

    def __init__(
        self,
        *,
        chat: UserInteractionChatPort | None,
        history_store: ChatHistoryStore,
        dispatch_morning_tasks: AsyncCommand,
        collect_evening_progress: AsyncCommand,
        cleanup_days: int = 30,
    ):
        self._chat = chat
        self._history_store = history_store
        self._dispatch_morning_tasks = dispatch_morning_tasks
        self._collect_evening_progress = collect_evening_progress
        self._cleanup_days = cleanup_days

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "chat":
            message = request.get("message", "")
            user_id = request.get("user_id", "anonymous")
            reply = await self._require_chat().chat(message=message, user_id=user_id)
            return {"reply": reply}
        if action == "chat_user_assistant":
            message = request.get("message", "")
            user_id = request.get("user_id", "anonymous")
            user_name = request.get("user_name", "")
            context = {
                "user_id": user_id,
                "user_name": user_name,
                "chat_id": request.get("chat_id", ""),
                "chat_type": request.get("chat_type", "p2p"),
            }
            reply = await self._require_chat().chat_with_user_assistant(
                message=message,
                user_id=user_id,
                user_name=user_name,
                context=context,
            )
            return {"reply": reply}
        if action == "clear_history":
            user_id = request.get("user_id", "")
            await self._require_chat().clear_history(user_id)
            return {"status": "cleared"}
        if action == "cleanup_conversations":
            deleted = await self._history_store.delete_inactive(days=self._cleanup_days)
            logger.info("conversation_cleanup_done", deleted=deleted)
            return {"status": "ok", "deleted": deleted}
        if action == "dispatch_morning_tasks":
            await self._dispatch_morning_tasks()
            return {"status": "ok"}
        if action == "collect_evening_progress":
            await self._collect_evening_progress()
            return {"status": "ok"}
        return unknown_action_error()

    def _require_chat(self) -> UserInteractionChatPort:
        if self._chat is None:
            raise RuntimeError("chat_service_not_initialized")
        return self._chat
