"""Application use cases for chat-agent readiness checks."""
from __future__ import annotations

from typing import Any

from .health_ports import ChatAgentHealthStore


class ChatAgentHealthUseCase:
    """Build chat-agent readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        health_store: ChatAgentHealthStore,
        chat_service: Any,
    ) -> None:
        self._health_store = health_store
        self._chat_service = chat_service

    async def check(self) -> dict[str, bool]:
        return {
            "database": await self._health_store.is_database_ready(),
            "chat_service": self._chat_service is not None,
        }
