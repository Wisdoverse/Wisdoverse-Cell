"""Conversation transcript aggregate for chat-agent history invariants."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ConversationHistoryTrimmed:
    """In-memory domain event raised when old transcript messages are removed."""

    user_id: str
    removed_count: int
    reason: str
    remaining_count: int


@dataclass(slots=True)
class ConversationTranscript:
    """Aggregate root for one user's persisted conversation transcript."""

    user_id: str
    messages: list[dict[str, Any]]
    pending_events: list[ConversationHistoryTrimmed] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("conversation transcript requires user_id")
        self.messages = [dict(message) for message in self.messages]

    def trim_to_message_limit(self, max_messages: int) -> "ConversationTranscript":
        """Keep the newest messages and remove any leading orphaned tool records."""
        if max_messages < 1:
            raise ValueError("max_messages must be positive")

        before = len(self.messages)
        if before > max_messages:
            self.messages = self.messages[-max_messages:]
            self._record_trim(
                removed_count=before - len(self.messages),
                reason="message_limit",
            )
        self.remove_leading_orphaned_tool_messages(reason="orphaned_tool_message")
        return self

    def trim_to_serialized_size(self, max_bytes: int) -> "ConversationTranscript":
        """Trim oldest messages until serialized transcript fits within max_bytes."""
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")

        before = len(self.messages)
        while self._serialized_size() > max_bytes and len(self.messages) > 1:
            self.messages.pop(0)
        if len(self.messages) != before:
            self._record_trim(
                removed_count=before - len(self.messages),
                reason="serialized_size",
            )
        self.remove_leading_orphaned_tool_messages(reason="orphaned_tool_message")
        return self

    def remove_leading_orphaned_tool_messages(
        self,
        *,
        reason: str,
    ) -> "ConversationTranscript":
        """Remove leading messages that would break tool-result replay."""
        removed = 0
        while self.messages:
            message = self.messages[0]
            if message.get("role") == "assistant":
                self.messages.pop(0)
                removed += 1
                continue

            content = message.get("content")
            if isinstance(content, list) and any(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in content
            ):
                self.messages.pop(0)
                removed += 1
                continue
            break

        if removed:
            self._record_trim(removed_count=removed, reason=reason)
        return self

    def pull_events(self) -> list[ConversationHistoryTrimmed]:
        """Drain pending domain events."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events

    def _serialized_size(self) -> int:
        return len(json.dumps(self.messages, ensure_ascii=False).encode("utf-8"))

    def _record_trim(self, *, removed_count: int, reason: str) -> None:
        self.pending_events.append(
            ConversationHistoryTrimmed(
                user_id=self.user_id,
                removed_count=removed_count,
                reason=reason,
                remaining_count=len(self.messages),
            )
        )


__all__ = [
    "ConversationHistoryTrimmed",
    "ConversationTranscript",
]
