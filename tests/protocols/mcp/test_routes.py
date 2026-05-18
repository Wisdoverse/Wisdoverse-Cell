"""Tests for MCP REST-style route error contracts."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.api import ApiErrorCode
from shared.protocols.mcp.server.base import MCPServer
from shared.protocols.mcp.server.router import MCPRouter
from shared.protocols.mcp.server.routes import create_mcp_router


@pytest.fixture
def client() -> TestClient:
    router = MCPRouter()

    @router.tool()
    def echo(text: str) -> str:
        return text

    @router.tool()
    def fail() -> str:
        raise RuntimeError("boom")

    @router.resource("config://app")
    def get_config() -> dict:
        return {"version": "1.0"}

    @router.prompt()
    def summarize(text: str) -> str:
        return f"Summarize {text}"

    server = MCPServer(name="test-mcp", router=router)
    app = FastAPI()
    app.include_router(create_mcp_router(server, prefix="/mcp"))
    return TestClient(app)


def test_call_tool_invalid_json_uses_error_contract(client: TestClient) -> None:
    response = client.post(
        "/mcp/tools/call",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_INVALID_JSON.value


def test_call_tool_missing_name_uses_error_contract(client: TestClient) -> None:
    response = client.post("/mcp/tools/call", json={"arguments": {}})

    assert response.status_code == 400
    assert response.json()["detail"] == "Tool name is required"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_TOOL_NAME_REQUIRED.value


def test_call_tool_not_found_uses_error_contract(client: TestClient) -> None:
    response = client.post("/mcp/tools/call", json={"name": "missing", "arguments": {}})

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool not found"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_TOOL_NOT_FOUND.value


def test_call_tool_execution_failed_uses_error_contract(client: TestClient) -> None:
    response = client.post("/mcp/tools/call", json={"name": "fail", "arguments": {}})

    assert response.status_code == 500
    assert response.json()["detail"] == "Tool execution failed"
    assert (
        response.headers["x-error-code"]
        == ApiErrorCode.MCP_TOOL_EXECUTION_FAILED.value
    )


def test_get_tool_schema_not_found_uses_error_contract(client: TestClient) -> None:
    response = client.get("/mcp/tools/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool not found"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_TOOL_NOT_FOUND.value


def test_read_resource_not_found_uses_error_contract(client: TestClient) -> None:
    response = client.get("/mcp/resources/read", params={"uri": "config://missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_RESOURCE_NOT_FOUND.value


def test_get_prompt_not_found_uses_error_contract(client: TestClient) -> None:
    response = client.post("/mcp/prompts/missing", json={"arguments": {}})

    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_PROMPT_NOT_FOUND.value


def test_get_prompt_schema_not_found_uses_error_contract(client: TestClient) -> None:
    response = client.get("/mcp/prompts/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"
    assert response.headers["x-error-code"] == ApiErrorCode.MCP_PROMPT_NOT_FOUND.value
