"""Tests for ControlPlanePlugin runtime ledger integration."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.app.plugins.control_plane import ControlPlanePlugin
from shared.control_plane.context import get_current_run_context
from shared.control_plane.tables import AgentRunTable, AuditEventTable
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


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
    assert [audit.action for audit in audits] == [
        "agent_run.started",
        "agent_run.succeeded",
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

    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error_category == "RuntimeError"
    assert runs[0].error_message == "handler exploded"
    assert runs[0].last_successful_step == "handler_started"
    assert [audit.action for audit in audits] == [
        "agent_run.started",
        "agent_run.failed",
    ]


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
