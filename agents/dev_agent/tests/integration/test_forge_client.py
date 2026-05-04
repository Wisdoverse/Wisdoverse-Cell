from unittest.mock import patch

import httpx
import pytest

from agents.dev_agent.adapters.agentforge_client import ForgeClient, ForgeClientError
from agents.dev_agent.models.schemas import WorkflowNode, WorkflowPlan


@pytest.fixture
def client():
    return ForgeClient(base_url="http://test:4010", token="test-token")


@pytest.mark.asyncio
async def test_create_workflow(client):
    plan = WorkflowPlan(
        name="test",
        description="test",
        nodes=[WorkflowNode(name="plan", config={"tags": ["plan"]})],
    )
    mock_resp = httpx.Response(200, json={"workflow": {"id": "wf-123"}})
    with patch.object(client._client, "request", return_value=mock_resp):
        wf_id = await client.create_workflow(plan)
        assert wf_id == "wf-123"


@pytest.mark.asyncio
async def test_get_status(client):
    mock_resp = httpx.Response(200, json={"status": "completed"})
    with patch.object(client._client, "request", return_value=mock_resp):
        status = await client.get_status("wf-123")
        assert status["status"] == "completed"


@pytest.mark.asyncio
async def test_server_error_records_failure(client):
    mock_resp = httpx.Response(503, text="Service Unavailable")
    with patch.object(client._client, "request", return_value=mock_resp):
        with pytest.raises(ForgeClientError):
            await client.get_status("wf-123")
    assert client._circuit_breaker._failure_count >= 1


@pytest.mark.asyncio
async def test_circuit_breaker_opens(client):
    mock_resp = httpx.Response(503, text="down")
    with patch.object(client._client, "request", return_value=mock_resp):
        for _ in range(5):
            try:
                await client.get_status("wf")
            except ForgeClientError:
                pass
    assert not client._circuit_breaker.can_execute()
