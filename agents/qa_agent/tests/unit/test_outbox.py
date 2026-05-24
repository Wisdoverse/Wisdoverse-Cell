"""QA outbox unit tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.qa_agent.core.outbox_ports import QAEventOutboxStore
from agents.qa_agent.db.repository import QAEventOutboxRepository
from agents.qa_agent.models import QAEventOutbox
from agents.qa_agent.models.schemas import QARunRequest
from agents.qa_agent.service.agent import QAAgent
from shared.schemas.event import Event, EventTypes


class AsyncSessionContext:
    """Minimal async context manager for mocked db sessions."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _db_manager_with_session():
    db_manager = MagicMock()
    db_manager.session.return_value = AsyncSessionContext(MagicMock())
    return db_manager


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_qa_01",
        "event_type": EventTypes.QA_ACCEPTANCE_COMPLETED,
        "source_agent": "qa-agent",
        "payload": {
            "run_id": "run_1",
            "agent_name": "dev_agent",
            "summary": {"l0_gate": "PASS"},
        },
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(spec=QAEventOutbox, **defaults)


class FakeQAEventOutboxStore(QAEventOutboxStore):
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added: list[Event] = []
        self.staged: list[Event] = []
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.last_limit: int | None = None

    async def add(self, event: Event) -> None:
        self.added.append(event)

    async def stage(self, session: object, event: Event) -> None:
        self.staged.append(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


@pytest.mark.asyncio
async def test_qa_outbox_repository_add_preserves_event_contract():
    session = MagicMock()
    session.flush = AsyncMock()
    repo = QAEventOutboxRepository(session)
    event = Event.create(
        event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
        source_agent="qa-agent",
        payload={
            "run_id": "run_1",
            "agent_name": "dev_agent",
            "summary": {"l0_gate": "PASS"},
        },
        trace_id="trace-qa",
    )

    row = await repo.add(event)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    assert row.event_id == event.event_id
    assert row.event_type == EventTypes.QA_ACCEPTANCE_COMPLETED
    assert row.source_agent == "qa-agent"
    assert row.payload["run_id"] == "run_1"
    assert row.trace_id == "trace-qa"
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_publish_pending_qa_events_marks_success():
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = FakeQAEventOutboxStore(rows=[_outbox_row()])
    agent = QAAgent(
        db=_db_manager_with_session(),
        bus=bus,
        event_publisher=publisher,
        runner=MagicMock(),
        notifier=MagicMock(),
        outbox_store=outbox_store,
    )

    result = await agent.publish_pending_qa_events(limit=5)

    assert outbox_store.last_limit == 5
    publisher.publish.assert_awaited_once()
    bus.publish.assert_not_awaited()
    event = publisher.publish.await_args.args[0]
    assert event.event_id == "evt_qa_01"
    assert event.event_type == EventTypes.QA_ACCEPTANCE_COMPLETED
    assert event.payload["run_id"] == "run_1"
    assert outbox_store.published == ["evt_qa_01"]
    assert outbox_store.failed == []
    assert result == {"total": 1, "published": 1, "failed": 0}


@pytest.mark.asyncio
async def test_publish_pending_qa_events_marks_failure_and_continues():
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=[RuntimeError("broker down"), True])
    failed_row = _outbox_row(event_id="evt_failed")
    ok_row = _outbox_row(event_id="evt_ok")
    outbox_store = FakeQAEventOutboxStore(rows=[failed_row, ok_row])
    agent = QAAgent(
        db=_db_manager_with_session(),
        bus=bus,
        event_publisher=publisher,
        runner=MagicMock(),
        notifier=MagicMock(),
        outbox_store=outbox_store,
    )

    result = await agent.publish_pending_qa_events(limit=2)

    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    assert outbox_store.failed == [("evt_failed", "broker down")]
    assert outbox_store.published == ["evt_ok"]
    assert result == {"total": 2, "published": 1, "failed": 1}


@pytest.mark.asyncio
async def test_run_acceptance_stages_events_before_notifier():
    db = _db_manager_with_session()
    bus = MagicMock()
    bus.publish = AsyncMock()
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    runner = MagicMock()
    runner.run_json = AsyncMock(
        return_value={
            "summary": {
                "l0_gate": "FAIL",
                "l1_check": "WARN",
                "l2_report": "INFO",
                "total_checks": 2,
                "l0_failures": 1,
                "l1_warnings": 1,
            },
            "results": [
                {
                    "level": "L0",
                    "category": "security",
                    "check": "secrets",
                    "status": "FAIL",
                }
            ],
            "duration_seconds": 3.0,
            "exit_code": 1,
        }
    )
    runner.run_markdown = AsyncMock(return_value=None)
    notifier = AsyncMock()
    notifier.notify_all = AsyncMock(return_value={"eventbus": {"sent": True}})
    outbox_store = FakeQAEventOutboxStore()
    agent = QAAgent(
        db=db,
        bus=bus,
        event_publisher=publisher,
        runner=runner,
        notifier=notifier,
        outbox_store=outbox_store,
    )

    request = QARunRequest(agent_name="dev_agent", trigger="api", requested_by="tester")

    def _save_result(*args, **kwargs):
        return SimpleNamespace(id=kwargs["run_id"])

    with (
        patch(
            "agents.qa_agent.core.acceptance_execution_use_cases.generate_ulid",
            return_value="run_1",
        ),
        patch(
            "agents.qa_agent.db.unit_of_work.SqlAlchemyQAReportStore.save_execution_result",
            new=AsyncMock(side_effect=_save_result),
        ),
    ):
        result = await agent.run_acceptance(request, trace_id="trace-qa")

    assert result.run_id == "run_1"
    assert len(outbox_store.staged) == 2
    staged_events = outbox_store.staged
    assert [event.event_type for event in staged_events] == [
        EventTypes.QA_ACCEPTANCE_COMPLETED,
        EventTypes.QA_GATE_FAILED,
    ]
    assert publisher.publish.await_count == 2
    bus.publish.assert_not_awaited()
    published_events = [call.args[0] for call in publisher.publish.await_args_list]
    assert published_events == staged_events
    assert outbox_store.published == [event.event_id for event in staged_events]
    assert outbox_store.failed == []
    notifier.notify_all.assert_awaited_once()
    eventbus_summary = notifier.notify_all.await_args.kwargs["eventbus_summary"]
    assert eventbus_summary == {"sent": True, "published": 2, "failed": 0}
