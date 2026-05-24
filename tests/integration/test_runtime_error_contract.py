"""Runtime-level API error envelope contract tests."""

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any

import pytest
from fastapi import APIRouter, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from shared.api import ERROR_CODE_HEADER, TRACE_ID_HEADER, ApiErrorCode, error_headers
from shared.app import create_agent_app
from shared.config import settings
from shared.schemas.agent import BaseAgent
from shared.schemas.error import ErrorResponse
from shared.schemas.event import Event

RUNTIME_APP_MODULES = [
    "agents.qa_agent.app.main",
    "agents.pjm_agent.app.main",
    "agents.dev_agent.app.main",
    "shared.capabilities.analysis.app.main",
    "shared.capabilities.sync.app.main",
    "services.gateways.channel.app.main",
    "services.gateways.user_interaction.app.main",
    "services.orchestration.coordinator.app.main",
]


class _ContractAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            agent_id="contract-agent",
            agent_name="Contract Agent",
        )

    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        return {"ok": True, "request": request}


class _ContractCommand(BaseModel):
    name: str
    count: int


def _assert_error_body(
    body: dict[str, Any],
    *,
    code: str,
    message: str,
    trace_id: str,
    detail: Any,
) -> ErrorResponse:
    envelope = ErrorResponse.model_validate(body)
    assert envelope.code == code
    assert envelope.message == message
    assert envelope.trace_id == trace_id
    assert body["detail"] == detail
    assert body["timestamp"] == envelope.timestamp
    datetime.fromisoformat(body["timestamp"])
    return envelope


def _create_contract_app():
    router = APIRouter(prefix="/contract")

    @router.get("/http-error")
    async def http_error():
        raise HTTPException(
            status_code=409,
            detail="domain_conflict",
            headers=error_headers(code="contract.domain_conflict"),
        )

    @router.post("/validation")
    async def validation_error(command: _ContractCommand):
        return command.model_dump()

    @router.get("/unexpected")
    async def unexpected_error():
        raise RuntimeError("database password leaked")

    return create_agent_app(
        _ContractAgent(),
        title="Contract Agent",
        routers=[router],
        include_api_key_middleware=False,
        evolution_enabled=False,
        harden_excluded=True,
    )


def _load_app(module_name: str) -> Any:
    return import_module(module_name).app


@pytest.mark.asyncio
async def test_create_agent_app_exposes_runtime_prometheus_metrics() -> None:
    app = _create_contract_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/agent/request", json={"action": "describe"})
        metrics_response = await client.get("/metrics")

    assert response.status_code == 200
    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain")
    metrics_body = metrics_response.text
    assert "wisdoverse_cell_http_requests_total" in metrics_body
    assert 'method="POST"' in metrics_body
    assert 'path="/agent/request"' in metrics_body
    assert 'status_code="200"' in metrics_body


@pytest.mark.asyncio
@pytest.mark.parametrize("module_name", RUNTIME_APP_MODULES)
async def test_runtime_apps_return_shared_error_envelope_for_auth_failures(
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every shared runtime app should expose the same API error envelope."""
    app = _load_app(module_name)
    trace_id = f"trace-contract-{module_name.rsplit('.', 2)[0].replace('.', '-')}"

    monkeypatch.setattr(settings, "internal_service_key", "contract-secret")
    monkeypatch.setattr(settings, "pm_api_key", "")
    monkeypatch.setattr(settings, "app_env", "test")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/agent/request",
            headers={TRACE_ID_HEADER: trace_id},
            json={"action": "describe"},
        )

    body = response.json()
    assert response.status_code == 401
    assert response.headers[ERROR_CODE_HEADER] == ApiErrorCode.INTERNAL_AUTH_UNAUTHORIZED.value
    assert response.headers[TRACE_ID_HEADER] == trace_id
    envelope = _assert_error_body(
        body,
        code=ApiErrorCode.INTERNAL_AUTH_UNAUTHORIZED.value,
        message="Unauthorized",
        trace_id=trace_id,
        detail="Unauthorized",
    )
    assert envelope.details is None


@pytest.mark.asyncio
async def test_create_agent_app_http_exception_uses_shared_error_envelope() -> None:
    """HTTPException responses keep legacy detail and add the structured body."""
    app = _create_contract_app()
    trace_id = "trace-contract-http-error"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/contract/http-error",
            headers={TRACE_ID_HEADER: trace_id},
        )

    assert response.status_code == 409
    assert response.headers[ERROR_CODE_HEADER] == "contract.domain_conflict"
    assert response.headers[TRACE_ID_HEADER] == trace_id
    envelope = _assert_error_body(
        response.json(),
        code="contract.domain_conflict",
        message="domain_conflict",
        trace_id=trace_id,
        detail="domain_conflict",
    )
    assert envelope.details is None


@pytest.mark.asyncio
async def test_create_agent_app_validation_errors_use_shared_error_envelope() -> None:
    """Request-validation failures expose a machine-readable details payload."""
    app = _create_contract_app()
    trace_id = "trace-contract-validation"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/contract/validation",
            headers={TRACE_ID_HEADER: trace_id},
            json={"name": "missing-count"},
        )

    body = response.json()
    assert response.status_code == 422
    assert response.headers[ERROR_CODE_HEADER] == ApiErrorCode.REQUEST_VALIDATION_FAILED.value
    assert response.headers[TRACE_ID_HEADER] == trace_id
    envelope = _assert_error_body(
        body,
        code=ApiErrorCode.REQUEST_VALIDATION_FAILED.value,
        message="Request validation failed",
        trace_id=trace_id,
        detail=body["detail"],
    )
    assert envelope.details is not None
    assert "errors" in envelope.details
    assert body["details"]["errors"][0]["loc"] == ["body", "count"]
    assert body["detail"][0]["loc"] == ["body", "count"]


@pytest.mark.asyncio
async def test_create_agent_app_unhandled_errors_are_sanitized() -> None:
    """Unhandled server errors must not leak internal exception details."""
    app = _create_contract_app()
    trace_id = "trace-contract-internal"

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/contract/unexpected",
            headers={TRACE_ID_HEADER: trace_id},
        )

    body = response.json()
    assert response.status_code == 500
    assert response.headers[ERROR_CODE_HEADER] == ApiErrorCode.INTERNAL_ERROR.value
    assert response.headers[TRACE_ID_HEADER] == trace_id
    envelope = _assert_error_body(
        body,
        code=ApiErrorCode.INTERNAL_ERROR.value,
        message="Internal service error. Please try again later.",
        trace_id=trace_id,
        detail="Internal service error. Please try again later.",
    )
    assert envelope.details is None
    assert "database password" not in str(body)
