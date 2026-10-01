"""HTTP adapter contract tests for the control-plane agent runner."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from shared.control_plane.agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from shared.control_plane.domain.agent_wakeup_adapter import AgentWakeupAdapterConfig


class _ResponseStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        await self.response.aclose()


def _response(body: dict | None = None, *, content: bytes | None = None, status: int = 200) -> httpx.Response:
    body_bytes = content if content is not None else json.dumps(body, allow_nan=True).encode()
    return httpx.Response(
        status,
        content=body_bytes,
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "http://agent.test/agent/request"),
    )


def _config(*, contract_version: str | None = None) -> AgentWakeupAdapterConfig:
    config = {"base_url": "http://agent.test"}
    if contract_version is not None:
        config["contract_version"] = contract_version
    return AgentWakeupAdapterConfig(
        agent_id="http-runner", adapter_type="http", config=config
    )


def _stream_patch(response: httpx.Response):
    return patch(
        "httpx.AsyncClient.stream",
        new_callable=MagicMock,
        return_value=_ResponseStream(response),
    )


@pytest.mark.asyncio
async def test_legacy_http_response_preserves_legacy_dispatch_and_trace_headers() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    response = _response({"status": "ok"})
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(response) as mock_stream,
    ):
        mock_settings.internal_service_key = "secret-key"
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        result = await runner._execute_http(
            _config(),
            {"action": "wakeup", "trace_id": "trace-runner-http", "run_id": "run-runner-http"},
        )

    assert result["status"] == "recorded"
    assert result["response"] == {"status": "ok"}
    headers = mock_stream.call_args.kwargs["headers"]
    assert headers["X-Internal-Key"] == "secret-key"
    assert headers["X-Trace-ID"] == "trace-runner-http"
    assert headers["Idempotency-Key"] == "run-runner-http"
    assert "X-Executor-Contract" not in headers


@pytest.mark.asyncio
async def test_http_v1_success_returns_bounded_contract_fields() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    response = _response(
        {
            "schema_version": "1.0",
            "status": "succeeded",
            "summary": "Generated the requested report",
            "cost_usd": 0.04,
            "output": {"report_id": "r-1"},
            "artifact_references": ["artifact://reports/r-1"],
        }
    )
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(response) as mock_stream,
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        result = await runner._execute_http(
            _config(contract_version="1.0"), {"run_id": "run-v1", "action": "wakeup"}
        )

    assert mock_stream.call_args.kwargs["headers"]["X-Executor-Contract"] == "1.0"
    assert result == {
        "status": "ok",
        "adapter": "http",
        "cost_usd": 0.04,
        "cost_is_estimate": False,
        "summary": "Generated the requested report",
        "response": {"report_id": "r-1"},
        "artifact_references": ["artifact://reports/r-1"],
    }


@pytest.mark.parametrize(
    "body",
    [
        {
            "schema_version": "2.0",
            "status": "succeeded",
            "summary": "wrong version",
            "cost_usd": 0,
            "output": {},
            "artifact_references": [],
        },
        {
            "schema_version": "1.0",
            "status": "succeeded",
            "summary": "nonfinite cost",
            "cost_usd": float("nan"),
            "output": {},
            "artifact_references": [],
        },
    ],
)
@pytest.mark.asyncio
async def test_http_v1_rejects_wrong_version_and_nonfinite_cost(body: dict) -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(_response(body)),
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        with pytest.raises(AgentWakeupError, match="executor_contract_invalid") as failure:
            await runner._execute_http(
                _config(contract_version="1.0"), {"run_id": "run-invalid", "action": "wakeup"}
            )
    assert failure.value.error_category == "uncertain_effects"


@pytest.mark.asyncio
async def test_http_v1_accepted_ack_is_recorded_not_business_success() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    response = _response(
        {
            "schema_version": "1.0",
            "status": "accepted",
            "summary": "Executor received the request",
            "cost_usd": 0,
            "output": {},
            "artifact_references": [],
        }
    )
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(response),
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        result = await runner._execute_http(
            _config(contract_version="1.0"), {"run_id": "run-accepted", "action": "wakeup"}
        )
    assert result["status"] == "recorded"


@pytest.mark.asyncio
async def test_http_v1_failed_result_is_an_explicit_execution_failure() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    response = _response(
        {
            "schema_version": "1.0",
            "status": "failed",
            "summary": "Executor rejected the requested operation",
            "cost_usd": 0.02,
            "output": {},
            "artifact_references": [],
        }
    )
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(response),
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        with pytest.raises(AgentWakeupError, match="http_executor_failed") as failure:
            await runner._execute_http(
                _config(contract_version="1.0"), {"run_id": "run-failed", "action": "wakeup"}
            )
    assert failure.value.error_category == "wakeup_error"


@pytest.mark.asyncio
async def test_http_invalid_json_is_uncertain_and_not_retried() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(_response(content=b"{invalid json")) as mock_stream,
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        with pytest.raises(AgentWakeupError, match="executor_contract_invalid") as failure:
            await runner._execute_http(
                _config(contract_version="1.0"), {"run_id": "run-invalid-json", "action": "wakeup"}
            )
    assert failure.value.error_category == "uncertain_effects"
    assert mock_stream.call_count == 1


@pytest.mark.asyncio
async def test_http_transport_timeout_is_uncertain_and_not_retried() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        patch(
            "httpx.AsyncClient.stream",
            new_callable=MagicMock,
            side_effect=httpx.ReadTimeout("response lost"),
        ) as mock_stream,
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        with pytest.raises(AgentWakeupError, match="executor_effects_uncertain") as failure:
            await runner._execute_http(
                _config(contract_version="1.0"), {"run_id": "run-uncertain", "action": "wakeup"}
            )
    assert failure.value.error_category == "uncertain_effects"
    assert mock_stream.call_count == 1


@pytest.mark.asyncio
async def test_http_server_error_is_ambiguous_and_not_retried() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    response = _response(status=503, content=b"executor may have run")
    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        _stream_patch(response) as mock_stream,
    ):
        mock_settings.control_plane_http_adapter_allowlist = "http://agent.test"
        with pytest.raises(AgentWakeupError, match="executor_effects_uncertain") as failure:
            await runner._execute_http(
                _config(contract_version="1.0"), {"run_id": "run-server-error", "action": "wakeup"}
            )
    assert failure.value.error_category == "uncertain_effects"
    assert mock_stream.call_count == 1
