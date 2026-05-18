"""Tests for A2A route error contracts."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.api import ApiErrorCode
from shared.protocols.a2a.server.jsonrpc import A2AJSONRPCServer
from shared.protocols.a2a.server.routes import create_a2a_router, mount_a2a_routes
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class DummyAgent(BaseAgent):
    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        return {}

    def get_a2a_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "dummy",
                "name": "Dummy",
                "description": "Dummy skill",
                "tags": ["test"],
            }
        ]


def _make_client(*, a2a_enabled: bool) -> TestClient:
    app = FastAPI()
    agent = DummyAgent(
        agent_id="dummy-agent",
        agent_name="Dummy Agent",
        a2a_enabled=a2a_enabled,
    )
    server = A2AJSONRPCServer()
    app.include_router(create_a2a_router(agent, server, prefix="/a2a"))
    return TestClient(app)


def test_agent_card_disabled_uses_error_contract() -> None:
    client = _make_client(a2a_enabled=False)

    response = client.get("/a2a/.well-known/agent.json")

    assert response.status_code == 501
    assert response.json()["detail"] == "A2A protocol not enabled for this agent"
    assert response.headers["x-error-code"] == ApiErrorCode.A2A_NOT_ENABLED.value


def test_task_stream_missing_task_uses_error_contract() -> None:
    client = _make_client(a2a_enabled=True)

    response = client.get("/a2a/tasks/task-missing/stream")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found: task-missing"
    assert response.headers["x-error-code"] == ApiErrorCode.A2A_TASK_NOT_FOUND.value


def test_root_agent_card_disabled_uses_error_contract() -> None:
    app = FastAPI()
    agent = DummyAgent(
        agent_id="dummy-agent",
        agent_name="Dummy Agent",
        a2a_enabled=False,
    )
    mount_a2a_routes(app, agent, A2AJSONRPCServer())
    client = TestClient(app)

    response = client.get("/.well-known/agent.json")

    assert response.status_code == 501
    assert response.json()["detail"] == "A2A protocol not enabled for this agent"
    assert response.headers["x-error-code"] == ApiErrorCode.A2A_NOT_ENABLED.value
