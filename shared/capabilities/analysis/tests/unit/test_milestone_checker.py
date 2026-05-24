"""
Unit Tests - MilestoneChecker

Tests milestone risk checks with a mocked projection port.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.config import AnalysisCoreConfig
from shared.capabilities.analysis.core.domain.projection import (
    SubtaskProgressProjection,
)


def _subtask_projection(
    record_id: str,
    *,
    feature_id: str,
    status: str,
    title: str,
) -> SubtaskProgressProjection:
    return SubtaskProgressProjection(
        parent_wp_id=1,
        subtask_record_id=record_id,
        subtask_status=status,
        completed="完成" in status or "Done" in status,
        updated_at=datetime.now(UTC),
        title=title,
        feature_id=feature_id,
    )


@pytest.fixture
def mock_projection():
    projection = AsyncMock()
    projection.list_subtask_progress = AsyncMock(return_value=[])
    return projection


@pytest.fixture
def mock_messenger():
    messenger = AsyncMock()
    messenger.send_message = AsyncMock(return_value={})
    return messenger


@pytest.fixture
def checker(mock_projection, mock_messenger):
    from shared.capabilities.analysis.core.milestone_checker import MilestoneChecker

    return MilestoneChecker(
        messenger=mock_messenger,
        projection_port=mock_projection,
        config=AnalysisCoreConfig.from_values(
            feishu_report_chat_id="chat_456",
            feishu_pm_app_token="token",
            feishu_pm_task_table_id="table",
        ),
    )


@pytest.mark.asyncio
async def test_check_no_tasks(checker, mock_projection):
    """No tasks should return an empty risk list."""
    mock_projection.list_subtask_progress.return_value = []

    risks = await checker.check()

    assert risks == []


@pytest.mark.asyncio
async def test_check_blocked_subtasks(checker, mock_projection):
    """Blocked subtasks should produce a blocked_subtasks risk."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection(
            "rec_1",
            feature_id="2266",
            status="阻塞(Blocked)",
            title="任务A",
        ),
        _subtask_projection(
            "rec_2",
            feature_id="2266",
            status="进行中(In Progress)",
            title="任务B",
        ),
    ]

    risks = await checker.check()

    blocked_risks = [r for r in risks if r["type"] == "blocked_subtasks"]
    assert len(blocked_risks) == 1
    assert blocked_risks[0]["severity"] == "warning"
    assert "任务A" in blocked_risks[0]["blocked_tasks"]


@pytest.mark.asyncio
async def test_check_multiple_blocked_is_critical(checker, mock_projection):
    """Multiple blocked subtasks should be critical."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection("rec_1", feature_id="100", status="阻塞(Blocked)", title="A"),
        _subtask_projection("rec_2", feature_id="100", status="Blocked", title="B"),
        _subtask_projection("rec_3", feature_id="100", status="进行中", title="C"),
    ]

    risks = await checker.check()

    blocked_risks = [r for r in risks if r["type"] == "blocked_subtasks"]
    assert len(blocked_risks) == 1
    assert blocked_risks[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_check_low_progress(checker, mock_projection):
    """Progress below 30% should produce a low_progress risk."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection("rec_1", feature_id="200", status="进行中", title="T1"),
        _subtask_projection("rec_2", feature_id="200", status="进行中", title="T2"),
        _subtask_projection("rec_3", feature_id="200", status="进行中", title="T3"),
        _subtask_projection("rec_4", feature_id="200", status="进行中", title="T4"),
    ]

    risks = await checker.check()

    progress_risks = [r for r in risks if r["type"] == "low_progress"]
    assert len(progress_risks) == 1
    assert "0%" in progress_risks[0]["message"]


@pytest.mark.asyncio
async def test_check_no_risk_when_all_completed(checker, mock_projection):
    """Completed tasks should not produce risks."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection("rec_1", feature_id="300", status="已完成(Done)", title="T1"),
        _subtask_projection("rec_2", feature_id="300", status="已完成(Done)", title="T2"),
    ]

    risks = await checker.check()

    assert risks == []


@pytest.mark.asyncio
async def test_push_risks_success(checker, mock_messenger):
    """Risk push should succeed with configured chat ID."""
    risks = [
        {"type": "blocked_subtasks", "severity": "critical", "message": "Feature #1: 2/3 阻塞", "blocked_tasks": ["A", "B"]},
    ]

    result = await checker.push_risks(risks)

    assert result is True
    mock_messenger.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_risks_empty(checker):
    """Empty risk list should not be pushed."""
    result = await checker.push_risks([])
    assert result is False


@pytest.mark.asyncio
async def test_push_risks_no_chat_id(mock_projection, mock_messenger):
    """Missing chat ID should skip risk push."""
    from shared.capabilities.analysis.core.milestone_checker import MilestoneChecker

    checker = MilestoneChecker(
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    result = await checker.push_risks([{"type": "test", "severity": "warning", "message": "x"}])
    assert result is False


@pytest.mark.asyncio
async def test_check_without_projection_data(mock_projection, mock_messenger):
    """Empty projection data should return empty risks."""
    from shared.capabilities.analysis.core.milestone_checker import MilestoneChecker

    checker = MilestoneChecker(
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    risks = await checker.check()

    assert risks == []
    mock_projection.list_subtask_progress.assert_called_once()
