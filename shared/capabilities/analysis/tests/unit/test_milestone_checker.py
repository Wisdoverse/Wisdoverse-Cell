"""
Unit Tests - MilestoneChecker

Tests milestone risk checks with a mocked Bitable port.
"""
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.config import AnalysisCoreConfig


@pytest.fixture
def mock_bitable():
    bitable = AsyncMock()
    bitable.list_all_records = AsyncMock(return_value=[])
    return bitable


@pytest.fixture
def mock_messenger():
    messenger = AsyncMock()
    messenger.send_message = AsyncMock(return_value={})
    return messenger


@pytest.fixture
def checker(mock_bitable, mock_messenger):
    from shared.capabilities.analysis.core.milestone_checker import MilestoneChecker

    return MilestoneChecker(
        bitable=mock_bitable,
        messenger=mock_messenger,
        config=AnalysisCoreConfig.from_values(
            feishu_report_chat_id="chat_456",
            feishu_pm_app_token="token",
            feishu_pm_task_table_id="table",
        ),
    )


@pytest.mark.asyncio
async def test_check_no_tasks(checker, mock_bitable):
    """No tasks should return an empty risk list."""
    mock_bitable.list_all_records.return_value = []

    risks = await checker.check()

    assert risks == []


@pytest.mark.asyncio
async def test_check_blocked_subtasks(checker, mock_bitable):
    """Blocked subtasks should produce a blocked_subtasks risk."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#2266", "状态": "阻塞(Blocked)", "任务(动宾短语)": "任务A"}},
        {"fields": {"关联 Feature ID (关键字段)": "#2266", "状态": "进行中(In Progress)", "任务(动宾短语)": "任务B"}},
    ]

    risks = await checker.check()

    blocked_risks = [r for r in risks if r["type"] == "blocked_subtasks"]
    assert len(blocked_risks) == 1
    assert blocked_risks[0]["severity"] == "warning"
    assert "任务A" in blocked_risks[0]["blocked_tasks"]


@pytest.mark.asyncio
async def test_check_multiple_blocked_is_critical(checker, mock_bitable):
    """Multiple blocked subtasks should be critical."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#100", "状态": "阻塞(Blocked)", "任务(动宾短语)": "A"}},
        {"fields": {"关联 Feature ID (关键字段)": "#100", "状态": "Blocked", "任务(动宾短语)": "B"}},
        {"fields": {"关联 Feature ID (关键字段)": "#100", "状态": "进行中", "任务(动宾短语)": "C"}},
    ]

    risks = await checker.check()

    blocked_risks = [r for r in risks if r["type"] == "blocked_subtasks"]
    assert len(blocked_risks) == 1
    assert blocked_risks[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_check_low_progress(checker, mock_bitable):
    """Progress below 30% should produce a low_progress risk."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T1"}},
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T2"}},
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T3"}},
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T4"}},
    ]

    risks = await checker.check()

    progress_risks = [r for r in risks if r["type"] == "low_progress"]
    assert len(progress_risks) == 1
    assert "0%" in progress_risks[0]["message"]


@pytest.mark.asyncio
async def test_check_no_risk_when_all_completed(checker, mock_bitable):
    """Completed tasks should not produce risks."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#300", "状态": "已完成(Done)", "任务(动宾短语)": "T1"}},
        {"fields": {"关联 Feature ID (关键字段)": "#300", "状态": "已完成(Done)", "任务(动宾短语)": "T2"}},
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
async def test_push_risks_no_chat_id(mock_bitable, mock_messenger):
    """Missing chat ID should skip risk push."""
    from shared.capabilities.analysis.core.milestone_checker import MilestoneChecker

    checker = MilestoneChecker(bitable=mock_bitable, messenger=mock_messenger)
    result = await checker.push_risks([{"type": "test", "severity": "warning", "message": "x"}])
    assert result is False


@pytest.mark.asyncio
async def test_check_no_config(mock_bitable, mock_messenger):
    """Missing app token should return empty risks."""
    from shared.capabilities.analysis.core.milestone_checker import MilestoneChecker

    checker = MilestoneChecker(bitable=mock_bitable, messenger=mock_messenger)
    risks = await checker.check()

    assert risks == []
    mock_bitable.list_all_records.assert_not_called()
