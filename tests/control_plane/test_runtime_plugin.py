"""Tests for ControlPlanePlugin runtime ledger integration."""

import hashlib
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.app.plugins.control_plane import ControlPlanePlugin
from shared.control_plane.agent_catalog import ORGANIZATION_ROLE_TEMPLATES, RUNTIME_MODULES
from shared.control_plane.context import get_current_run_context
from shared.control_plane.tables import (
    AgentRoleTable,
    AgentRunTable,
    ArtifactTable,
    AuditEventTable,
)
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes


class RecordingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="recording-agent",
            agent_name="Recording Agent",
            subscribed_events=["work.execute"],
            published_events=["work.done"],
        )

    async def handle_event(self, event: Event) -> list[Event]:
        run_context = get_current_run_context()
        return [
            self.create_event(
                "work.done",
                {
                    "company_id": event.payload.get("company_id"),
                    "ok": True,
                    "run_id": run_context.run_id if run_context else None,
                },
                trace_id=event.metadata.trace_id,
            )
        ]

    async def handle_request(self, request: dict) -> dict:
        return {"ok": True}


class FailingAgent(RecordingAgent):
    async def handle_event(self, event: Event) -> list[Event]:
        raise RuntimeError("handler exploded")


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def _provider() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
        await db_session.flush()

    return _provider


async def _runs(db_session: AsyncSession) -> list[AgentRunTable]:
    result = await db_session.execute(select(AgentRunTable))
    return list(result.scalars().all())


async def _audits(db_session: AsyncSession) -> list[AuditEventTable]:
    result = await db_session.execute(
        select(AuditEventTable).order_by(AuditEventTable.created_at)
    )
    return list(result.scalars().all())


async def _artifacts(db_session: AsyncSession) -> list[ArtifactTable]:
    result = await db_session.execute(select(ArtifactTable))
    return list(result.scalars().all())


async def _roles(db_session: AsyncSession) -> list[AgentRoleTable]:
    result = await db_session.execute(select(AgentRoleTable))
    return list(result.scalars().all())


def _evidence_hash(artifact: ArtifactTable) -> str:
    payload = json.dumps(
        artifact.metadata_json["evidence"],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_records_successful_event_run(db_session: AsyncSession):
    plugin = ControlPlanePlugin(
        session_provider=_session_provider(db_session),
        default_company_id="cmp_test",
    )
    wrapped = plugin.wrap_agent(RecordingAgent())
    event = Event.create(
        event_type="work.execute",
        source_agent="test",
        payload={"company_id": "cmp_test", "task": "build ledger"},
        trace_id="trace_success",
    )

    output_events = await wrapped.handle_event(event)

    runs = await _runs(db_session)
    audits = await _audits(db_session)
    artifacts = await _artifacts(db_session)

    assert len(output_events) == 1
    assert len(runs) == 1
    assert runs[0].agent_id == "recording-agent"
    assert runs[0].status == "succeeded"
    assert runs[0].trace_id == "trace_success"
    assert runs[0].trigger_event_id == event.event_id
    assert runs[0].input_event["metadata"]["trace_id"] == "trace_success"
    assert runs[0].completed_at is not None
    assert runs[0].output_events[0]["event_type"] == "work.done"
    assert runs[0].output_events[0]["metadata"]["trace_id"] == "trace_success"
    assert runs[0].output_events[0]["payload"]["run_id"] == runs[0].run_id
    assert {audit.trace_id for audit in audits} == {"trace_success"}
    assert {audit.action for audit in audits} == {
        EventTypes.AGENT_RUN_STARTED,
        EventTypes.AGENT_RUN_SUCCEEDED,
        EventTypes.ARTIFACT_CREATED,
    }
    assert len(artifacts) == 1
    assert artifacts[0].run_id == runs[0].run_id
    assert artifacts[0].artifact_type == "run_walkthrough"
    assert artifacts[0].content_hash == _evidence_hash(artifacts[0])
    assert artifacts[0].metadata_json["generated_by"] == "control_plane_runtime_plugin"
    assert artifacts[0].metadata_json["evidence"]["status"] == "succeeded"
    assert artifacts[0].metadata_json["evidence"]["events"]["input_event_id"] == (
        event.event_id
    )
    assert artifacts[0].metadata_json["evidence"]["events"]["output_event_ids"] == [
        output_events[0].event_id
    ]


@pytest.mark.asyncio
async def test_records_failed_event_run_and_reraises(db_session: AsyncSession):
    plugin = ControlPlanePlugin(
        session_provider=_session_provider(db_session),
        default_company_id="cmp_test",
    )
    wrapped = plugin.wrap_agent(FailingAgent())
    event = Event.create(
        event_type="work.execute",
        source_agent="test",
        payload={"company_id": "cmp_test", "task": "explode"},
        trace_id="trace_failed",
    )

    with pytest.raises(RuntimeError, match="handler exploded"):
        await wrapped.handle_event(event)

    runs = await _runs(db_session)
    audits = await _audits(db_session)
    artifacts = await _artifacts(db_session)

    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error_category == "RuntimeError"
    assert runs[0].error_message == "handler exploded"
    assert runs[0].last_successful_step == "handler_started"
    assert runs[0].output_events[0]["event_type"] == EventTypes.AGENT_RUN_FAILED
    assert runs[0].output_events[0]["payload"]["error_category"] == "RuntimeError"
    assert {audit.action for audit in audits} == {
        EventTypes.AGENT_RUN_STARTED,
        EventTypes.AGENT_RUN_FAILED,
        EventTypes.ARTIFACT_CREATED,
    }
    assert len(artifacts) == 1
    assert artifacts[0].run_id == runs[0].run_id
    assert artifacts[0].content_hash == _evidence_hash(artifacts[0])
    assert artifacts[0].metadata_json["evidence"]["status"] == "failed"
    assert artifacts[0].metadata_json["evidence"]["error_category"] == "RuntimeError"


@pytest.mark.asyncio
async def test_control_plane_failure_is_fail_open_by_default(db_session: AsyncSession):
    @asynccontextmanager
    async def broken_provider():
        raise RuntimeError("db unavailable")
        yield db_session

    plugin = ControlPlanePlugin(
        session_provider=broken_provider,
        default_company_id="cmp_test",
    )
    wrapped = plugin.wrap_agent(RecordingAgent())
    event = Event.create(
        event_type="work.execute",
        source_agent="test",
        payload={"company_id": "cmp_test"},
        trace_id="trace_fail_open",
    )

    output_events = await wrapped.handle_event(event)

    assert len(output_events) == 1
    assert await _runs(db_session) == []


@pytest.mark.asyncio
async def test_control_plane_plugin_bootstraps_core_role_agents(
    db_session: AsyncSession,
):
    plugin = ControlPlanePlugin(
        session_provider=_session_provider(db_session),
        default_company_id="cmp_plugin",
    )

    await plugin.startup(SimpleNamespace(agent_id="recording-agent"))
    await plugin.startup(SimpleNamespace(agent_id="recording-agent"))

    roles = await _roles(db_session)
    audits = await _audits(db_session)
    expected_agent_ids = {
        template.agent_id for template in ORGANIZATION_ROLE_TEMPLATES
    } | {module.agent_id for module in RUNTIME_MODULES if module.frontend_managed}

    assert {role.agent_id for role in roles} == expected_agent_ids
    assert {role.adapter_type for role in roles} == {"builtin"}
    assert {role.target_id for role in audits} == expected_agent_ids
    assert len(audits) == len(expected_agent_ids)
