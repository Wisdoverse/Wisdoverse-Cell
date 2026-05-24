"""Tests for the QA AcceptanceRun aggregate."""

from datetime import UTC, datetime

import pytest

from agents.qa_agent.core.domain.acceptance_run import (
    AcceptanceRun,
    AcceptanceRunCompleted,
    AcceptanceRunStatus,
    InvalidAcceptanceRunError,
)
from agents.qa_agent.core.domain.acceptance_vocabulary import (
    GATE_FAIL,
    GATE_PASS,
    L1_PASS,
    L1_WARN,
    L2_INFO,
)
from shared.core.identifiers import AcceptanceRunId


def _summary(*, failing: bool = False) -> dict:
    return {
        "l0_gate": GATE_FAIL if failing else GATE_PASS,
        "l1_check": L1_WARN if failing else L1_PASS,
        "l2_report": L2_INFO,
        "total_checks": 2,
        "l0_failures": 1 if failing else 0,
        "l1_warnings": 1 if failing else 0,
    }


def _findings() -> list[dict]:
    return [
        {
            "level": "L0",
            "category": "security",
            "check": "secrets",
            "status": "FAIL",
        },
        {
            "level": "L1",
            "category": "style",
            "check": "lint",
            "status": "WARN",
        },
    ]


def test_acceptance_run_completion_raises_domain_event() -> None:
    completed_at = datetime(2026, 5, 23, tzinfo=UTC)

    run = AcceptanceRun.request(
        run_id=AcceptanceRunId("qarun_test"),
        agent_name="dev_agent",
        commit_sha="abc123",
        mr_iid=12,
        gitlab_project_id=34,
        trigger="api",
        level="all",
        requested_at=completed_at,
    )
    assert run.status is AcceptanceRunStatus.REQUESTED

    run.start(started_at=completed_at)
    assert run.status is AcceptanceRunStatus.RUNNING

    run.record_completion(
        summary=_summary(failing=True),
        findings=_findings(),
        duration_seconds=3.0,
        report_markdown="## Report",
        completed_at=completed_at,
    )

    assert run.status is AcceptanceRunStatus.COMPLETED
    assert run.is_blocking is True
    events = run.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, AcceptanceRunCompleted)
    assert event.run_id == AcceptanceRunId("qarun_test")
    assert event.target == "agents/dev_agent"
    assert event.verdict.is_blocking is True
    assert event.blocking_findings == [_findings()[0]]
    assert event.completed_at == completed_at
    assert run.pull_events() == []


def test_acceptance_run_completion_factory_uses_lifecycle() -> None:
    completed_at = datetime(2026, 5, 23, tzinfo=UTC)

    run = AcceptanceRun.complete(
        run_id=AcceptanceRunId("qarun_factory"),
        agent_name="dev_agent",
        commit_sha=None,
        mr_iid=None,
        gitlab_project_id=None,
        trigger="api",
        level="all",
        summary=_summary(),
        findings=[],
        duration_seconds=1.0,
        report_markdown=None,
        completed_at=completed_at,
    )

    assert run.status is AcceptanceRunStatus.COMPLETED
    assert run.requested_at == completed_at
    assert run.started_at == completed_at
    assert run.completed_at == completed_at
    assert isinstance(run.pull_events()[0], AcceptanceRunCompleted)


def test_acceptance_run_rejects_invalid_transitions() -> None:
    run = AcceptanceRun.request(
        run_id=AcceptanceRunId("qarun_transitions"),
        agent_name="dev_agent",
        commit_sha=None,
        mr_iid=None,
        gitlab_project_id=None,
        trigger="api",
        level="all",
    )

    with pytest.raises(InvalidAcceptanceRunError):
        run.record_completion(
            summary=_summary(),
            findings=[],
            duration_seconds=1.0,
            report_markdown=None,
        )

    run.start()
    run.record_completion(
        summary=_summary(),
        findings=[],
        duration_seconds=1.0,
        report_markdown=None,
    )
    with pytest.raises(InvalidAcceptanceRunError):
        run.start()


def test_acceptance_run_completion_rejects_invalid_counts() -> None:
    summary = _summary(failing=True)
    summary["total_checks"] = 1

    with pytest.raises(InvalidAcceptanceRunError):
        AcceptanceRun.complete(
            run_id=AcceptanceRunId("qarun_invalid"),
            agent_name="dev_agent",
            commit_sha=None,
            mr_iid=None,
            gitlab_project_id=None,
            trigger="api",
            level="all",
            summary=summary,
            findings=_findings(),
            duration_seconds=3.0,
            report_markdown=None,
        )


def test_acceptance_run_completion_rejects_missing_identity() -> None:
    with pytest.raises(InvalidAcceptanceRunError):
        AcceptanceRun.complete(
            run_id=AcceptanceRunId(""),
            agent_name="dev_agent",
            commit_sha=None,
            mr_iid=None,
            gitlab_project_id=None,
            trigger="api",
            level="all",
            summary=_summary(),
            findings=[],
            duration_seconds=0.1,
            report_markdown=None,
        )
