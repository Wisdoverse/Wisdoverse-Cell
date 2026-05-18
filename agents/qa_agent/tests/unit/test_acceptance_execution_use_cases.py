from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.qa_agent.core.acceptance_execution_use_cases import (
    QAAcceptanceExecutionUseCase,
    build_acceptance_events,
    derive_severity,
)
from agents.qa_agent.models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceSummary,
    QARunRequest,
)
from shared.schemas.event import EventTypes


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Db:
    def __init__(self, session=None):
        self.session_obj = session or object()

    def session(self):
        return _SessionContext(self.session_obj)


def _report(l0_gate: str = "PASS") -> dict:
    return {
        "summary": {
            "l0_gate": l0_gate,
            "l1_check": "WARN" if l0_gate == "FAIL" else "PASS",
            "l2_report": "INFO",
            "total_checks": 2,
            "l0_failures": 1 if l0_gate == "FAIL" else 0,
            "l1_warnings": 1 if l0_gate == "FAIL" else 0,
        },
        "results": [
            {
                "level": "L0",
                "category": "security",
                "check": "secrets",
                "status": "FAIL",
            }
        ]
        if l0_gate == "FAIL"
        else [],
        "duration_seconds": 3.0,
        "exit_code": 1 if l0_gate == "FAIL" else 0,
    }


def _request(**overrides) -> QARunRequest:
    defaults = {
        "agent_name": "dev_agent",
        "trigger": "api",
        "requested_by": "tester",
    }
    defaults.update(overrides)
    return QARunRequest(**defaults)


def _run_record(**overrides):
    defaults = {
        "id": "run_1",
        "agent_name": "dev_agent",
        "commit_sha": None,
        "mr_iid": None,
        "trigger": "api",
        "level": "all",
        "files_changed": [],
        "l0_status": "PASS",
        "l1_status": "PASS",
        "l2_status": "INFO",
        "total_checks": 2,
        "l0_failure_count": 0,
        "l1_warning_count": 0,
        "duration_seconds": 3.0,
        "runner_exit_code": 0,
        "raw_report": {"results": []},
        "report_markdown": None,
        "notification_summary": {"eventbus": {"sent": True}},
        "created_at": None,
        "completed_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _use_case(
    *,
    runner=None,
    notifier=None,
    run_store=None,
    report_store=None,
    stage_event=None,
    publish_staged=None,
    record_metrics=None,
    duplicate_error_types: tuple[type[BaseException], ...] = (),
) -> tuple[QAAcceptanceExecutionUseCase, SimpleNamespace]:
    if runner is None:
        runner = AsyncMock()
        runner.run_json = AsyncMock(return_value=_report())
        runner.run_markdown = AsyncMock(return_value="## Report")
    if notifier is None:
        notifier = AsyncMock()
        notifier.notify_all = AsyncMock(return_value={"eventbus": {"sent": True}})
    if run_store is None:
        run_store = AsyncMock()
        run_store.get_by_trigger_event_id = AsyncMock(return_value=None)
        run_store.update_notification_summary = AsyncMock(return_value=True)
    if report_store is None:
        report_store = AsyncMock()
        report_store.save_execution_result = AsyncMock(return_value=_run_record())
    if stage_event is None:
        stage_event = AsyncMock()
    if publish_staged is None:
        publish_staged = AsyncMock(
            return_value={"sent": True, "published": 1, "failed": 0}
        )
    if record_metrics is None:
        record_metrics = MagicMock()

    context = SimpleNamespace(
        runner=runner,
        notifier=notifier,
        run_store=run_store,
        report_store=report_store,
        stage_event=stage_event,
        publish_staged=publish_staged,
        record_metrics=record_metrics,
    )
    use_case = QAAcceptanceExecutionUseCase(
        db_manager=_Db(),
        runner=runner,
        notifier=notifier,
        run_store=run_store,
        report_store_factory=lambda _session: report_store,
        stage_event=stage_event,
        publish_staged_events=publish_staged,
        record_metrics=record_metrics,
        duplicate_persist_error_types=duplicate_error_types,
    )
    return use_case, context


@pytest.mark.asyncio
async def test_run_acceptance_persists_stages_publishes_and_notifies() -> None:
    runner = AsyncMock()
    runner.run_json = AsyncMock(return_value=_report("FAIL"))
    runner.run_markdown = AsyncMock(return_value="## Failing report")
    use_case, context = _use_case(runner=runner)

    result = await use_case.run_acceptance(
        _request(mr_iid=12, gitlab_project_id=34),
        trace_id="trace-qa",
        trigger_event_id="evt_qa",
    )

    assert result.run_id == "run_1"
    assert result.summary.l0_gate == "FAIL"
    context.run_store.get_by_trigger_event_id.assert_awaited_once_with("evt_qa")
    context.report_store.save_execution_result.assert_awaited_once()
    assert context.stage_event.await_count == 2
    staged_events = [call.args[1] for call in context.stage_event.await_args_list]
    assert [event.event_type for event in staged_events] == [
        EventTypes.QA_ACCEPTANCE_COMPLETED,
        EventTypes.QA_GATE_FAILED,
    ]
    context.publish_staged.assert_awaited_once_with(staged_events, "run_1")
    context.notifier.notify_all.assert_awaited_once()
    assert context.notifier.notify_all.await_args.kwargs["eventbus_summary"] == {
        "sent": True,
        "published": 1,
        "failed": 0,
    }
    context.run_store.update_notification_summary.assert_awaited_once()
    context.record_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_replayed_event_returns_existing_run_without_side_effects() -> None:
    run_store = AsyncMock()
    run_store.get_by_trigger_event_id = AsyncMock(return_value=_run_record())
    use_case, context = _use_case(run_store=run_store)

    result = await use_case.run_acceptance(
        _request(),
        trigger_event_id="evt_replayed",
    )

    assert result.run_id == "run_1"
    context.runner.run_json.assert_not_awaited()
    context.report_store.save_execution_result.assert_not_awaited()
    context.notifier.notify_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_persist_race_returns_existing_run() -> None:
    class DuplicatePersistError(Exception):
        pass

    run_store = AsyncMock()
    run_store.get_by_trigger_event_id = AsyncMock(
        side_effect=[None, _run_record(id="run_existing")]
    )
    report_store = AsyncMock()
    report_store.save_execution_result = AsyncMock(
        side_effect=DuplicatePersistError("duplicate")
    )
    use_case, context = _use_case(
        run_store=run_store,
        report_store=report_store,
        duplicate_error_types=(DuplicatePersistError,),
    )

    result = await use_case.run_acceptance(
        _request(),
        trigger_event_id="evt_race",
    )

    assert result.run_id == "run_existing"
    assert run_store.get_by_trigger_event_id.await_count == 2
    context.notifier.notify_all.assert_not_awaited()
    context.publish_staged.assert_not_awaited()


def test_build_acceptance_events_adds_gate_failed_for_l0_failures() -> None:
    report = _report("FAIL")
    result = AcceptanceExecutionResult(
        success=False,
        exit_code=1,
        summary=AcceptanceSummary(
            l0_gate="FAIL",
            l1_check="WARN",
            l2_report="INFO",
            total_checks=2,
            l0_failures=1,
            l1_warnings=1,
        ),
        duration_seconds=3.0,
    )

    events = build_acceptance_events(
        run_id="run_1",
        request=_request(mr_iid=12, gitlab_project_id=34),
        result=result,
        summary=report["summary"],
        findings=report["results"],
        report_markdown="## Report",
        trace_id="trace-qa",
    )

    assert [event.event_type for event in events] == [
        EventTypes.QA_ACCEPTANCE_COMPLETED,
        EventTypes.QA_GATE_FAILED,
    ]
    assert events[0].metadata.trace_id == "trace-qa"
    assert events[1].payload["blocking_findings"] == report["results"]


def test_derive_severity_maps_runner_findings() -> None:
    assert derive_severity({"level": "L0", "status": "FAIL"}) == "critical"
    assert derive_severity({"level": "L1", "status": "WARN"}) == "medium"
    assert derive_severity({"level": "L2", "status": "INFO"}) == "info"
    assert derive_severity({"level": "L0", "status": "PASS"}) == "low"
