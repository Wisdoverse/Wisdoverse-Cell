"""Ports for chat-agent runtime dependencies."""

from collections.abc import AsyncIterator, Sequence
from datetime import date
from typing import Any, Protocol, runtime_checkable


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


# ─── Conversation engine ports (DDD-017 seed) ─────────────────────────────
#
# Per ``ddd-compliance-audit.md`` row DDD-017 and
# ``architecture-principles.md`` §1 Domain layer, the user-interaction
# core/ layer must not import from ``shared.infra``. The ports below
# wrap the conversation-engine infrastructure so ``chat_service.py``
# (and any successor in the future chat-agent runtime per DDD-016)
# depends on the application boundary rather than the concrete engine.
#
# This is a **seed** PR: the Protocols ship here; chat_service migration
# follows in a dedicated PR so the rewrite stays reviewable per
# ``architecture-principles.md`` §3.


@runtime_checkable
class ConversationEnginePort(Protocol):
    """One conversational turn behind a typed port.

    Implementations consume a system prompt, prior message history,
    and tool definitions; produce a stream of typed events terminating
    in a ``TurnCompleteEvent``-shaped value. The concrete
    ``shared.infra.conversation_engine.ConversationEngine`` satisfies
    this Protocol structurally.
    """

    messages: list[dict[str, Any]]

    def run(self, user_message: str) -> AsyncIterator[Any]:
        """Drive one conversational turn; yield typed turn events."""


@runtime_checkable
class ConversationEngineFactory(Protocol):
    """Factory that produces one engine instance per turn.

    Wired at the application layer (`app/`) so `chat_service.py`
    never imports the concrete engine. Takes the per-turn knobs
    (system prompt, history, tools-callable, tool-executor closure)
    and returns a ConversationEnginePort.
    """

    def __call__(
        self,
        *,
        system_prompt: str,
        history: list[dict[str, Any]],
        tools_provider: Any,
        tool_executor: Any,
        compressor: Any,
        max_tool_calls: int,
        agent_id: str,
    ) -> ConversationEnginePort:
        """Construct one ConversationEnginePort for one turn."""
