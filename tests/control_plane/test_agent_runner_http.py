"""HTTP adapter contract tests for the control-plane agent runner."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from shared.control_plane.agent_runner import ControlPlaneAgentRunner


@pytest.mark.asyncio
async def test_http_adapter_propagates_internal_key_and_trace_id() -> None:
    runner = ControlPlaneAgentRunner(repo=object())
    response = httpx.Response(
        200,
        json={"status": "ok"},
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "http://agent.test/agent/request"),
    )

    with (
        patch("shared.control_plane.agent_runner.settings") as mock_settings,
        patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=response,
        ) as mock_post,
    ):
        mock_settings.internal_service_key = "secret-key"

        result = await runner._execute_http(
            {"base_url": "http://agent.test"},
            {"action": "wakeup", "trace_id": "trace-runner-http"},
        )

    assert result["response"] == {"status": "ok"}
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["X-Internal-Key"] == "secret-key"
    assert headers["X-Trace-ID"] == "trace-runner-http"
