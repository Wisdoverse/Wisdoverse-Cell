from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.dev_agent.core.event_use_cases import DevEventUseCase
from agents.dev_agent.models.schemas import RiskLevel, SanitizedTask
from shared.schemas.event import Event, EventTypes


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Factory:
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="dev-agent",
            payload=payload,
            trace_id=trace_id,
        )


class _Sanitizer:
    def sanitize(self, task_input):
        return SanitizedTask(**task_input.model_dump())


class _RiskAssessor:
    def __init__(self, risk: RiskLevel = RiskLevel.MEDIUM):
        self._risk = risk

    def assess(self, task: SanitizedTask) -> RiskLevel:
        return self._risk


def _use_case(
    *,
    risk: RiskLevel = RiskLevel.MEDIUM,
    has_db=True,
    session=None,
    repo=None,
    log_repo=None,
    collector=None,
    task_processor=None,
) -> tuple[DevEventUseCase, SimpleNamespace]:
    session = session or AsyncMock()
    session.commit = AsyncMock()
    repo = repo or AsyncMock()
    log_repo = log_repo or AsyncMock()
    task_processor = task_processor or AsyncMock(return_value=[])

    context = SimpleNamespace(
        session=session,
        repo=repo,
        log_repo=log_repo,
        collector=collector,
        task_processor=task_processor,
    )
    use_case = DevEventUseCase(
        sanitizer=_Sanitizer(),
        risk_assessor=_RiskAssessor(risk),
        has_db=lambda: has_db,
        session_factory=lambda: _SessionContext(session),
        repo_factory=lambda _session: repo,
        log_repo_factory=lambda _session: log_repo,
        result_collector_factory=lambda _repo, _log_repo: collector,
        task_processor=task_processor,
        event_factory=_Factory(),
    )
    return use_case, context


@pytest.mark.asyncio
async def test_unknown_event_returns_no_events() -> None:
    use_case, _ = _use_case()

    result = await use_case.handle(
        Event.create(
            event_type="unknown.event",
            source_agent="test",
            payload={},
        )
    )

    assert result == []


@pytest.mark.asyncio
async def test_tasks_ready_rejects_critical_task_without_database() -> None:
    use_case, context = _use_case(risk=RiskLevel.CRITICAL, has_db=False)

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="pjm-agent",
            payload={
                "wp_id": 1,
                "tasks": [
                    {
                        "id": 11,
                        "title": "Database migration",
                        "description": "Run alembic migration",
                        "estimated_hours": 2,
                    }
                ],
            },
            trace_id="trace-dev",
        )
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.DEV_TASK_FAILED
    assert result[0].source_agent == "dev-agent"
    assert result[0].metadata.trace_id == "trace-dev"
    assert result[0].payload["wp_id"] == 11
    assert "CRITICAL risk" in result[0].payload["error"]
    context.task_processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_tasks_ready_processes_sanitized_tasks_and_commits() -> None:
    task_event = Event.create(
        event_type=EventTypes.DEV_WORKFLOW_CREATED,
        source_agent="dev-agent",
        payload={"task_id": "dev-123"},
        trace_id="trace-dev",
    )
    processor = AsyncMock(return_value=[task_event])
    use_case, context = _use_case(task_processor=processor)

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="pjm-agent",
            payload={
                "wp_id": 100,
                "tasks": [
                    {
                        "id": 123,
                        "title": "Implement endpoint",
                        "description": "Add route",
                        "estimated_hours": 3,
                    }
                ],
            },
            trace_id="trace-dev",
        )
    )

    assert result == [task_event]
    context.session.commit.assert_awaited_once()
    processor.assert_awaited_once()
    sanitized = processor.await_args.args[0]
    assert sanitized.wp_id == 123
    assert processor.await_args.args[1] == RiskLevel.MEDIUM
    assert processor.await_args.args[2] is context.repo
    assert processor.await_args.args[3] is context.log_repo
    assert processor.await_args.kwargs["trace_id"] == "trace-dev"


@pytest.mark.asyncio
async def test_qa_result_handles_reviewing_task_and_commits() -> None:
    task = SimpleNamespace(id="dev-1", status="reviewing", mr_iid=7)
    repo = AsyncMock()
    repo.get_by_mr_iid = AsyncMock(return_value=task)
    result_event = Event.create(
        event_type=EventTypes.DEV_TASK_COMPLETED,
        source_agent="dev-agent",
        payload={"task_id": "dev-1"},
    )
    collector = AsyncMock()
    collector.handle_qa_result = AsyncMock(return_value=[result_event])
    use_case, context = _use_case(repo=repo, collector=collector)

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
            source_agent="qa-agent",
            payload={"mr_iid": 7, "summary": {"l0_gate": "PASS"}},
            trace_id="trace-qa",
        )
    )

    assert result == [result_event]
    repo.get_by_mr_iid.assert_awaited_once_with(7)
    collector.handle_qa_result.assert_awaited_once_with(
        task,
        {"mr_iid": 7, "summary": {"l0_gate": "PASS"}},
    )
    context.session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_qa_result_missing_mr_iid_returns_no_events() -> None:
    repo = AsyncMock()
    use_case, context = _use_case(repo=repo)

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
            source_agent="qa-agent",
            payload={},
        )
    )

    assert result == []
    repo.get_by_mr_iid.assert_not_awaited()
    context.session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_qa_result_ignores_wrong_task_status() -> None:
    repo = AsyncMock()
    repo.get_by_mr_iid = AsyncMock(
        return_value=SimpleNamespace(id="dev-1", status="executing")
    )
    collector = AsyncMock()
    use_case, context = _use_case(repo=repo, collector=collector)

    result = await use_case.handle(
        Event.create(
            event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
            source_agent="qa-agent",
            payload={"mr_iid": 7},
        )
    )

    assert result == []
    collector.handle_qa_result.assert_not_awaited()
    context.session.commit.assert_not_awaited()
