"""QA application facade tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.qa_agent.core.application_facade import QAApplicationFacade
from agents.qa_agent.models.schemas import QARunRequest, QARunStats
from shared.core.identifiers import AcceptanceRunId
from shared.schemas.event import Event, EventTypes


def _facade(
    *,
    acceptance_execution: MagicMock | None = None,
    run_queries: MagicMock | None = None,
    outbox_delivery: MagicMock | None = None,
) -> QAApplicationFacade:
    return QAApplicationFacade(
        acceptance_execution=acceptance_execution or MagicMock(),
        run_queries=run_queries or MagicMock(),
        outbox_delivery=outbox_delivery or MagicMock(),
    )


@pytest.mark.asyncio
async def test_qa_application_facade_runs_acceptance_use_case():
    acceptance_execution = MagicMock()
    result = MagicMock()
    acceptance_execution.run_acceptance = AsyncMock(return_value=result)
    request = QARunRequest(agent_name="dev_agent", trigger="api", requested_by="qa")
    facade = _facade(acceptance_execution=acceptance_execution)

    actual = await facade.run_acceptance(
        request,
        trace_id="trace_1",
        trigger_event_id="evt_1",
    )

    assert actual is result
    acceptance_execution.run_acceptance.assert_awaited_once_with(
        request,
        trace_id="trace_1",
        trigger_event_id="evt_1",
    )


@pytest.mark.asyncio
async def test_qa_application_facade_delegates_run_queries():
    run_queries = MagicMock()
    run_queries.list_runs = AsyncMock(return_value=[{"id": "run_1"}])
    run_queries.get_run = AsyncMock(return_value={"id": "run_1"})
    stats = QARunStats(
        days=7,
        total_runs=0,
        pass_runs=0,
        warn_runs=0,
        failed_runs=0,
        l0_fail_rate=0.0,
        avg_duration_seconds=0.0,
    )
    run_queries.get_stats = AsyncMock(return_value=stats)
    facade = _facade(run_queries=run_queries)

    assert await facade.list_runs(agent_name="dev_agent", limit=5, offset=1) == [{"id": "run_1"}]
    assert await facade.get_run(AcceptanceRunId("run_1")) == {"id": "run_1"}
    assert await facade.get_stats(agent_name="dev_agent", days=7) is stats

    run_queries.list_runs.assert_awaited_once_with(
        agent_name="dev_agent",
        limit=5,
        offset=1,
    )
    run_queries.get_run.assert_awaited_once_with(AcceptanceRunId("run_1"))
    run_queries.get_stats.assert_awaited_once_with(agent_name="dev_agent", days=7)


@pytest.mark.asyncio
async def test_qa_application_facade_delegates_outbox_delivery():
    outbox_delivery = MagicMock()
    outbox_delivery.publish_pending_events = AsyncMock(
        return_value={"total": 1, "published": 1, "failed": 0},
    )
    outbox_delivery.publish_event_via_outbox = AsyncMock(return_value=True)
    event = Event.create(
        event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
        source_agent="qa-agent",
        payload={"run_id": "run_1"},
    )
    facade = _facade(outbox_delivery=outbox_delivery)

    assert await facade.publish_pending_qa_events(limit=3) == {
        "total": 1,
        "published": 1,
        "failed": 0,
    }
    assert await facade.publish_event_via_outbox(event) is True

    outbox_delivery.publish_pending_events.assert_awaited_once_with(limit=3)
    outbox_delivery.publish_event_via_outbox.assert_awaited_once_with(event)
