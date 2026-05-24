"""Health-check ports for chat-agent readiness."""

from __future__ import annotations

from typing import Protocol


class ChatAgentHealthStore(Protocol):
    """Database readiness boundary for chat-agent health checks."""

    async def is_database_ready(self) -> bool:
        """Return whether the chat-agent database is reachable."""
