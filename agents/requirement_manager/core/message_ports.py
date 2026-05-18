"""Ports for Requirement chat-message persistence."""

from typing import Any, Protocol


class RequirementMessageStore(Protocol):
    """Persistence port for chat messages used by session extraction."""

    async def create(self, message: Any) -> Any:
        """Persist a chat message."""

    async def get_by_feishu_message_id(self, feishu_message_id: str) -> Any | None:
        """Return one chat message by Feishu message id."""

    async def get_by_session(self, session_id: str) -> list[Any]:
        """Return all messages for a chat session."""

    async def count_by_session(self, session_id: str) -> int:
        """Return how many messages belong to a chat session."""

    async def mark_extracted(self, session_id: str, requirement_ids: list[str]) -> int:
        """Mark session messages as extracted and linked to requirements."""
