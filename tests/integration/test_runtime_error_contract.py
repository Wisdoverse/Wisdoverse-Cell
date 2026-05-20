"""Runtime-level API error envelope contract tests."""

from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from shared.api import ERROR_CODE_HEADER, TRACE_ID_HEADER, ApiErrorCode
from shared.config import settings

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


def _load_app(module_name: str) -> Any:
    return import_module(module_name).app


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
    assert body["detail"] == "Unauthorized"
    assert body["code"] == ApiErrorCode.INTERNAL_AUTH_UNAUTHORIZED.value
    assert body["message"] == "Unauthorized"
    assert body["trace_id"] == trace_id
    assert body["details"] is None
    assert body["timestamp"]
