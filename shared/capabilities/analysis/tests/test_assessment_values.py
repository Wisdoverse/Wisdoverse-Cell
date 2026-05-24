"""Tests for Analysis assessment domain value objects."""

from datetime import UTC, datetime

import pytest

from shared.capabilities.analysis.core.domain.assessment import (
    AnalysisMilestoneTaskSnapshot,
    AnalysisQualityVerdict,
    AnalysisRiskSeverity,
    AnalysisRiskType,
    DeliverableQualityTask,
    InvalidAnalysisAssessmentError,
    MilestoneRiskSignal,
    QualityEvaluation,
)
from shared.capabilities.analysis.core.domain.projection import (
    SubtaskProgressProjection,
)


def test_milestone_task_snapshot_classifies_statuses() -> None:
    blocked = AnalysisMilestoneTaskSnapshot.from_fields(
        {
            "关联 Feature ID (关键字段)": "#2266",
            "状态": "阻塞(Blocked)",
            "任务(动宾短语)": "Prepare launch checklist",
        }
    )

    assert blocked.feature_id == "2266"
    assert blocked.has_feature is True
    assert blocked.is_blocked is True
    assert blocked.is_completed is False

    completed = AnalysisMilestoneTaskSnapshot.from_fields({"状态": "已完成(Done)"})
    assert completed.is_completed is True


def test_milestone_task_snapshot_translates_projection_row() -> None:
    snapshot = AnalysisMilestoneTaskSnapshot.from_projection(
        SubtaskProgressProjection(
            parent_wp_id=42,
            subtask_record_id="rec_feature",
            subtask_status="阻塞(Blocked)",
            completed=False,
            updated_at=datetime.now(UTC),
            title="Prepare launch checklist",
            feature_id="#2266",
        )
    )

    assert snapshot.feature_id == "2266"
    assert snapshot.title == "Prepare launch checklist"
    assert snapshot.is_blocked is True


def test_milestone_risk_signal_returns_legacy_event_payload() -> None:
    signal = MilestoneRiskSignal.blocked_subtasks(
        feature_id="#100",
        total=3,
        blocked_tasks=["Task A", "Task B"],
    )

    assert signal.severity is AnalysisRiskSeverity.CRITICAL
    assert signal.risk_type is AnalysisRiskType.BLOCKED_SUBTASKS
    assert signal.to_event_payload() == {
        "feature_id": "100",
        "type": "blocked_subtasks",
        "severity": "critical",
        "risk_level": "critical",
        "message": "Feature #100: 2/3 子任务阻塞",
        "blocked_tasks": ["Task A", "Task B"],
    }


def test_quality_task_snapshot_sanitizes_prompt_metadata() -> None:
    task = DeliverableQualityTask.from_bitable_record(
        {
            "record_id": "rec_1",
            "fields": {
                "任务(动宾短语)": "Prepare PRD",
                "状态": "进行中",
                "交付物/产出链接": "https://example.feishu.cn/docx/abc?token=secret",
                "验收标准": "Must include risks.",
                "进度": "50%",
            },
        }
    )

    assert task is not None
    assert task.record_id == "rec_1"
    assert task.to_prompt_metadata() == {
        "task_name": "Prepare PRD",
        "status": "进行中",
        "deliverable_link_present": True,
        "deliverable_link_domain": "example.feishu.cn",
        "acceptance_hint": "Must include risks.",
        "progress": "50%",
    }


def test_quality_task_snapshot_skips_already_scored_tasks() -> None:
    task = DeliverableQualityTask.from_bitable_record(
        {
            "record_id": "rec_2",
            "fields": {
                "交付物/产出链接": "https://example.feishu.cn/docx/def",
                "交付物质量": "合格",
            },
        }
    )

    assert task is None


def test_quality_evaluation_validates_verdict_and_writeback_payload() -> None:
    evaluation = QualityEvaluation.from_llm_payload(
        {
            "quality": "合格",
            "comment": "Metadata is sufficient.",
            "confidence": 0.7,
        }
    )

    assert evaluation.verdict is AnalysisQualityVerdict.ACCEPTABLE
    assert evaluation.quality == "合格"
    assert evaluation.to_write_back_fields() == {
        "交付物质量": "合格",
        "质量评语": "Metadata is sufficient.",
    }


def test_quality_evaluation_rejects_unknown_verdict() -> None:
    with pytest.raises(InvalidAnalysisAssessmentError):
        QualityEvaluation.from_llm_payload(
            {
                "quality": "pass",
                "comment": "ok",
                "confidence": 0.8,
            }
        )
