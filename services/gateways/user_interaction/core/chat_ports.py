"""Ports for user-interaction chat runtime dependencies."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol


class ChatLLM(Protocol):
    """LLM gateway contract needed by chat runtime and context compression."""

    async def create_messages(self, **kwargs):
        """Create a tool-capable chat response."""

    async def complete(self, **kwargs) -> str:
        """Generate a plain-text completion for context summarization."""


class ChatHistoryStore(Protocol):
    """Persistence port for chat conversation history."""

    async def get_by_user(self, user_id: str) -> list[dict] | None:
        """Return stored messages for a user."""

    async def save(self, user_id: str, messages: list[dict]) -> None:
        """Persist the user's conversation history."""

    async def clear(self, user_id: str) -> None:
        """Delete the user's stored conversation history."""

    async def delete_inactive(self, days: int = 30) -> int:
        """Delete inactive conversation history rows and return the count."""


class DailyProgressContextItem(Protocol):
    """Minimal daily-progress fields needed by the chat prompt context."""

    id: int
    status: str
    task_title: str


class DailyProgressContextStore(Protocol):
    """Read port for pending daily-progress context."""

    async def get_pending(
        self,
        user_id: str,
        target_date: date,
    ) -> Sequence[DailyProgressContextItem]:
        """Return pending progress rows for a user and date."""


class InMemoryChatHistoryStore:
    """Volatile chat history store used by tests and explicit in-memory setups."""

    def __init__(self):
        self._messages_by_user: dict[str, list[dict]] = {}

    async def get_by_user(self, user_id: str) -> list[dict] | None:
        messages = self._messages_by_user.get(user_id)
        return list(messages) if messages is not None else None

    async def save(self, user_id: str, messages: list[dict]) -> None:
        self._messages_by_user[user_id] = list(messages)

    async def clear(self, user_id: str) -> None:
        self._messages_by_user.pop(user_id, None)

    async def delete_inactive(self, days: int = 30) -> int:
        return 0


class EmptyDailyProgressContextStore:
    """Daily-progress context store that returns no pending progress."""

    async def get_pending(
        self,
        user_id: str,
        target_date: date,
    ) -> Sequence[DailyProgressContextItem]:
        return []


class UnconfiguredChatLLM:
    """LLM placeholder used when no runtime LLM is explicitly injected."""

    async def create_messages(self, **kwargs):
        raise RuntimeError("chat LLM dependency is not configured")

    async def complete(self, **kwargs) -> str:
        raise RuntimeError("chat LLM dependency is not configured")
