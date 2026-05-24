"""Tests for user-interaction gateway compatibility API proxies."""

from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from services.gateways.user_interaction.api import bitable, daily_progress


class FakeChatAgentClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_daily_progress(
        self,
        *,
        target_date: date | None,
        user_id: str,
        days: int,
    ) -> dict:
        self.calls.append(
            (
                "daily_progress",
                {
                    "target_date": target_date,
                    "user_id": user_id,
                    "days": days,
                },
            )
        )
        return {"entries": [], "total": 0}

    async def confirm_bitable_update(self, payload: dict) -> dict:
        self.calls.append(("confirm", payload))
        return {"status": "confirmed"}

    async def reject_bitable_operation(self, payload: dict) -> dict:
        self.calls.append(("reject", payload))
        return {"status": "rejected"}

    async def create_bitable_record(self, payload: dict) -> dict:
        self.calls.append(("create", payload))
        return {"status": "created"}


@pytest.fixture
def fake_client(monkeypatch) -> FakeChatAgentClient:
    client = FakeChatAgentClient()
    monkeypatch.setattr(daily_progress, "get_chat_agent_client", lambda: client)
    monkeypatch.setattr(bitable, "get_chat_agent_client", lambda: client)
    return client


@pytest.fixture
def proxy_app() -> FastAPI:
    app = FastAPI()
    app.include_router(daily_progress.router)
    app.include_router(bitable.router)
    return app


@pytest.mark.asyncio
async def test_daily_progress_proxy_calls_chat_agent_client(
    proxy_app: FastAPI,
    fake_client: FakeChatAgentClient,
) -> None:
    transport = ASGITransport(app=proxy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/daily-progress",
            params={"target_date": "2026-05-17", "user_id": "u_1", "days": 2},
        )

    assert response.status_code == 200
    assert response.json() == {"entries": [], "total": 0}
    assert fake_client.calls == [
        (
            "daily_progress",
            {"target_date": date(2026, 5, 17), "user_id": "u_1", "days": 2},
        )
    ]


@pytest.mark.asyncio
async def test_bitable_proxy_calls_chat_agent_client(
    proxy_app: FastAPI,
    fake_client: FakeChatAgentClient,
) -> None:
    transport = ASGITransport(app=proxy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        confirm = await client.post(
            "/api/bitable/confirm",
            json={"record_id": "rec_1", "fields": {"status": "done"}},
        )
        reject = await client.post(
            "/api/bitable/reject",
            json={"record_id": "rec_1", "action_type": "update"},
        )
        create = await client.post(
            "/api/bitable/create",
            json={"fields": {"title": "Task"}},
        )

    assert confirm.json() == {"status": "confirmed"}
    assert reject.json() == {"status": "rejected"}
    assert create.json() == {"status": "created"}
    assert fake_client.calls == [
        (
            "confirm",
            {
                "record_id": "rec_1",
                "fields": {"status": "done"},
                "table_id": "",
                "user_id": "",
                "user_name": "",
                "action_id": "",
            },
        ),
        (
            "reject",
            {
                "action_type": "update",
                "user_id": "",
                "user_name": "",
                "fields": {},
                "table_id": "",
                "record_id": "rec_1",
            },
        ),
        (
            "create",
            {
                "fields": {"title": "Task"},
                "table_id": "",
                "user_id": "",
                "user_name": "",
                "action_id": "",
            },
        ),
    ]
