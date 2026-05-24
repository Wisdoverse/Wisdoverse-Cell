"""HTTP adapter from the user-interaction gateway to chat-agent."""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlencode

from shared.config import settings
from shared.infra.agent_client import AgentClient


class ChatAgentRequestClient:
    """Call the chat-agent request API through the service boundary."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: AgentClient | None = None,
    ) -> None:
        self._client = client or AgentClient(base_url or settings.chat_agent_url)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        trace_id = request.get("trace_id")
        return await self._client.post(
            "/api/v1/chat-agent/requests",
            json=request,
            trace_id=trace_id if isinstance(trace_id, str) else None,
        )

    async def list_daily_progress(
        self,
        *,
        target_date: date | None,
        user_id: str,
        days: int,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"days": days}
        if target_date is not None:
            params["target_date"] = target_date.isoformat()
        if user_id:
            params["user_id"] = user_id
        return await self._client.get(f"/api/daily-progress?{urlencode(params)}")

    async def confirm_bitable_update(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._client.post("/api/bitable/confirm", json=payload)

    async def reject_bitable_operation(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._client.post("/api/bitable/reject", json=payload)

    async def create_bitable_record(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._client.post("/api/bitable/create", json=payload)


_chat_agent_client: ChatAgentRequestClient | None = None


def get_chat_agent_client() -> ChatAgentRequestClient:
    """Return the process-local chat-agent HTTP client singleton."""
    global _chat_agent_client
    if _chat_agent_client is None:
        _chat_agent_client = ChatAgentRequestClient()
    return _chat_agent_client
