"""End-to-end control-plane API flows against an in-process FastAPI app."""

import sys
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.api import create_control_plane_router


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def _provider():
        yield db_session
        await db_session.flush()

    return _provider


@pytest.mark.asyncio
async def test_goal_to_agent_run_to_artifact_timeline_e2e(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_enabled",
        True,
    )
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_allowlist",
        "process:ops-runner",
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        goal = await client.post(
            "/api/v1/control-plane/goals",
            json={
                "company_id": "cmp_e2e",
                "title": "Complete SPEC control plane",
                "status": "active",
                "success_metric": "Traceable outcome exists",
                "created_by": "human:board",
            },
        )
        goal_id = goal.json()["goal_id"]

        work_item = await client.post(
            "/api/v1/control-plane/work-items",
            json={
                "company_id": "cmp_e2e",
                "title": "Run governed execution",
                "status": "ready",
                "priority": "critical",
                "goal_id": goal_id,
                "owner_agent_id": "ops-runner",
                "created_by": "human:board",
            },
        )
        work_item_id = work_item.json()["work_item_id"]

        agent = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_e2e",
                "agent_id": "ops-runner",
                "display_name": "Ops Runner",
                "adapter_type": "process",
                "adapter_config": {
                    "command": [
                        sys.executable,
                        "-c",
                        "import json,sys; data=json.load(sys.stdin); print(data['work_item_id'])",
                    ],
                    "timeout_sec": 10,
                },
                "created_by": "human:board",
            },
        )

        wake = await client.post(
            "/api/v1/control-plane/agents/ops-runner/wake",
            json={
                "company_id": "cmp_e2e",
                "actor_id": "human:board",
                "trace_id": "trace-e2e",
                "goal_id": goal_id,
                "work_item_id": work_item_id,
                "input": {"task": "produce handoff"},
            },
        )
        run_id = wake.json()["run"]["run_id"]

        decision = await client.post(
            "/api/v1/control-plane/decisions",
            json={
                "company_id": "cmp_e2e",
                "title": "Accept run output",
                "rationale": "The agent completed the requested handoff.",
                "status": "accepted",
                "run_id": run_id,
                "work_item_id": work_item_id,
                "goal_id": goal_id,
                "selected_option": "accept",
                "decided_by": "human:board",
                "created_by": "human:board",
            },
        )

        artifact = await client.post(
            "/api/v1/control-plane/artifacts",
            json={
                "company_id": "cmp_e2e",
                "artifact_type": "run_walkthrough",
                "title": "E2E run walkthrough",
                "uri": "artifact://e2e/run-walkthrough",
                "run_id": run_id,
                "work_item_id": work_item_id,
                "goal_id": goal_id,
                "created_by_agent_id": "ops-runner",
                "created_by": "agent:ops-runner",
            },
        )

        trace_timeline = await client.get(
            "/api/v1/control-plane/timeline",
            params={"company_id": "cmp_e2e", "trace_id": "trace-e2e"},
        )
        run_timeline = await client.get(
            "/api/v1/control-plane/timeline",
            params={"company_id": "cmp_e2e", "run_id": run_id},
        )

    assert goal.status_code == 201
    assert work_item.status_code == 201
    assert agent.status_code == 201
    assert wake.status_code == 200
    assert wake.json()["run"]["status"] == "succeeded"
    assert wake.json()["run"]["goal_id"] == goal_id
    assert wake.json()["run"]["work_item_id"] == work_item_id
    assert wake.json()["output"]["stdout"].strip() == work_item_id
    assert decision.status_code == 201
    assert decision.json()["run_id"] == run_id
    assert artifact.status_code == 201
    assert artifact.json()["run_id"] == run_id
    assert trace_timeline.status_code == 200
    assert run_timeline.status_code == 200
    assert {"agent_run", "audit_event", "artifact", "decision"}.issubset(
        {item["type"] for item in trace_timeline.json()["timeline"]}
    )
    assert {"agent_run", "audit_event", "artifact", "decision"}.issubset(
        {item["type"] for item in run_timeline.json()["timeline"]}
    )
