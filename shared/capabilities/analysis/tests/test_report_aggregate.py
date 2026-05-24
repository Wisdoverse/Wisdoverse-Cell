"""Tests for Analysis report domain objects."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shared.capabilities.analysis.core.domain.feishu_task import (
    AnalysisFeishuTaskSnapshot,
)
from shared.capabilities.analysis.core.domain.projection import WorkPackageProjection
from shared.capabilities.analysis.core.domain.report import (
    AnalysisReportKind,
    AnalysisReportStats,
    AnalysisReportStatus,
    GeneratedAnalysisReport,
    InvalidAnalysisReportError,
    InvalidAnalysisReportTransitionError,
    TaskSourceStats,
)


def _feishu_task(status: str) -> AnalysisFeishuTaskSnapshot:
    return AnalysisFeishuTaskSnapshot.from_fields({"状态": status})


def _wp(wp_id: int, status: str) -> WorkPackageProjection:
    return WorkPackageProjection(
        wp_id=wp_id,
        project_id=1,
        subject=f"Work package {wp_id}",
        type_name="Task",
        status_name=status,
        percentage_done=100 if status == "closed" else 20,
        assigned_to=None,
        parent_id=None,
        due_date=None,
        updated_at=datetime.now(UTC),
        extra={},
    )


def test_report_stats_are_immutable_value_objects() -> None:
    """Report statistics validate source totals before formatting."""
    stats = AnalysisReportStats.from_sources(
        feishu_tasks=[
            _feishu_task("已完成(Done)"),
            _feishu_task("进行中(In Progress)"),
            _feishu_task("阻塞(Blocked)"),
        ],
        op_tasks=[_wp(1, "closed"), _wp(2, "In progress")],
    )

    assert stats.total == 5
    assert stats.feishu == TaskSourceStats(
        total=3,
        completed=1,
        in_progress=1,
        blocked=1,
    )
    assert stats.op == TaskSourceStats(total=2, completed=1, in_progress=1)
    assert stats.to_legacy_dict() == {
        "total": 5,
        "feishu": {
            "total": 3,
            "completed": 1,
            "in_progress": 1,
            "blocked": 1,
        },
        "op": {
            "total": 2,
            "completed": 1,
            "in_progress": 1,
        },
    }

    with pytest.raises(InvalidAnalysisReportError):
        TaskSourceStats(total=1, completed=1, in_progress=1)


def test_report_stats_classify_each_source_row_once() -> None:
    """Messy source statuses do not double-count a single task row."""
    stats = AnalysisReportStats.from_sources(
        feishu_tasks=[_feishu_task("阻塞(Blocked) / 进行中(In Progress)")],
        op_tasks=[_wp(1, "closed in progress")],
    )

    assert stats.feishu == TaskSourceStats(total=1, completed=0, in_progress=0, blocked=1)
    assert stats.op == TaskSourceStats(total=1, completed=0, in_progress=1)


def test_generated_report_raises_domain_event_and_legacy_payload() -> None:
    """Generated reports are aggregate roots with a domain-event buffer."""
    generated_at = datetime(2026, 5, 23, tzinfo=UTC)
    stats = AnalysisReportStats(
        feishu=TaskSourceStats(total=1, completed=1, in_progress=0),
        op=TaskSourceStats(total=0, completed=0, in_progress=0),
    )
    report = GeneratedAnalysisReport.generate(
        report_kind=AnalysisReportKind.DAILY,
        content="Daily content",
        summary="共 1 个任务",
        stats=stats,
        generated_at=generated_at,
    )

    assert report.status == AnalysisReportStatus.GENERATED
    assert report.to_response(include_stats=True)["stats"]["total"] == 1

    events = report.pull_events()
    assert [event.event_name for event in events] == ["AnalysisReportGenerated"]
    assert events[0].to_payload() == {
        "report_kind": "daily",
        "summary": "共 1 个任务",
        "total_tasks": 1,
        "occurred_at": generated_at.isoformat(),
    }
    assert report.pull_events() == []


def test_report_status_transition_guards() -> None:
    """Report lifecycle transitions are explicit."""
    report = GeneratedAnalysisReport.generate(
        report_kind=AnalysisReportKind.WEEKLY,
        content="Weekly content",
        summary="共 0 个任务",
        stats=None,
    )

    report.mark_pushed(pushed_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert report.status == AnalysisReportStatus.PUSHED
    assert report.pushed_at is not None

    with pytest.raises(InvalidAnalysisReportTransitionError):
        report.mark_failed()

    with pytest.raises(InvalidAnalysisReportError):
        GeneratedAnalysisReport.generate(
            report_kind=AnalysisReportKind.DAILY,
            content="",
            summary="missing content",
            stats=None,
        )
