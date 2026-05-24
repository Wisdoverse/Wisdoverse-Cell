"""Tests for the gateway to chat-agent HTTP adapter."""

from datetime import date

import pytest

from services.gateways.user_interaction.adapters.chat_agent_client import (
    ChatAgentRequestClient,
)


class FakeAgentClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None, str | None]] = []

    async def post(self, path: str, json: dict | None = None, *, trace_id: str | None = None):
        self.calls.append(("post", path, json or {}, trace_id))
        return {"reply": "ok"}

    async def get(self, path: str, *, trace_id: str | None = None):
        self.calls.append(("get", path, None, trace_id))
        return {"entries": [], "total": 0}


@pytest.mark.asyncio
async def test_chat_agent_request_client_posts_to_internal_request_boundary() -> None:
    fake = FakeAgentClient()
    client = ChatAgentRequestClient(client=fake)

    result = await client.handle_request(
        {"action": "chat_user_assistant", "message": "hello", "trace_id": "tr_1"}
    )

    assert result == {"reply": "ok"}
    assert fake.calls == [
        (
            "post",
            "/api/v1/chat-agent/requests",
            {"action": "chat_user_assistant", "message": "hello", "trace_id": "tr_1"},
            "tr_1",
        )
    ]


@pytest.mark.asyncio
async def test_chat_agent_request_client_gets_daily_progress() -> None:
    fake = FakeAgentClient()
    client = ChatAgentRequestClient(client=fake)

    result = await client.list_daily_progress(
        target_date=date(2026, 5, 17),
        user_id="u_1",
        days=2,
    )

    assert result == {"entries": [], "total": 0}
    assert fake.calls == [
        (
            "get",
            "/api/daily-progress?days=2&target_date=2026-05-17&user_id=u_1",
            None,
            None,
        )
    ]


@pytest.mark.asyncio
async def test_chat_agent_request_client_posts_bitable_operations() -> None:
    fake = FakeAgentClient()
    client = ChatAgentRequestClient(client=fake)

    await client.confirm_bitable_update({"record_id": "rec_1"})
    await client.reject_bitable_operation({"record_id": "rec_1"})
    await client.create_bitable_record({"fields": {"name": "Task"}})

    assert fake.calls == [
        ("post", "/api/bitable/confirm", {"record_id": "rec_1"}, None),
        ("post", "/api/bitable/reject", {"record_id": "rec_1"}, None),
        ("post", "/api/bitable/create", {"fields": {"name": "Task"}}, None),
    ]
