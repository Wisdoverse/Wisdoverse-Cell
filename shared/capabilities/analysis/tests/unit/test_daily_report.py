"""
Unit Tests - DailyReportGenerator

Tests daily report generation with mocked projection ports.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.config import AnalysisCoreConfig
from shared.capabilities.analysis.core.domain.feishu_task import (
    AnalysisFeishuTaskSnapshot,
)
from shared.capabilities.analysis.core.domain.projection import (
    SubtaskProgressProjection,
)


def _feishu_task(
    *,
    title: str = "任务",
    status: str,
    blocked_reason: str = "",
) -> AnalysisFeishuTaskSnapshot:
    return AnalysisFeishuTaskSnapshot.from_fields(
        {
            "任务(动宾短语)": title,
            "状态": status,
            "阻塞原因": blocked_reason,
        }
    )


def _subtask_projection(
    record_id: str,
    *,
    title: str = "任务",
    status: str,
    blocked_reason: str = "",
) -> SubtaskProgressProjection:
    return SubtaskProgressProjection(
        parent_wp_id=1,
        subtask_record_id=record_id,
        subtask_status=status,
        completed="完成" in status or "Done" in status,
        updated_at=datetime.now(UTC),
        title=title,
        blocked_reason=blocked_reason,
    )


@pytest.fixture
def mock_projection():
    projection = AsyncMock()
    projection.list_work_packages = AsyncMock(return_value=[])
    projection.list_subtask_progress = AsyncMock(return_value=[])
    return projection


@pytest.fixture
def mock_messenger():
    messenger = AsyncMock()
    messenger.send_message = AsyncMock(return_value={})
    return messenger


@pytest.fixture
def generator(mock_messenger, mock_projection):
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    return DailyReportGenerator(
        messenger=mock_messenger,
        projection_port=mock_projection,
        config=AnalysisCoreConfig.from_values(
            feishu_report_chat_id="chat_123",
            feishu_pm_app_token="token",
            feishu_pm_task_table_id="table",
        ),
    )


@pytest.mark.asyncio
async def test_generate_empty(generator, mock_projection):
    """No task data should return an empty report."""
    mock_projection.list_subtask_progress.return_value = []

    result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    assert result["summary"] == "无数据"
    assert result["stats"] == {}


@pytest.mark.asyncio
async def test_generate_with_tasks(generator, mock_projection):
    """Task data should generate a stats report."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection("rec_1", title="完成设计", status="已完成(Done)"),
        _subtask_projection("rec_2", title="开发功能A", status="进行中(In Progress)"),
        _subtask_projection(
            "rec_3",
            title="修复BugX",
            status="阻塞(Blocked)",
            blocked_reason="等待API",
        ),
        _subtask_projection("rec_4", title="编写文档", status="未开始"),
    ]

    result = await generator.generate()

    stats = result["stats"]
    assert stats["total"] == 4
    assert stats["feishu"]["completed"] == 1
    assert stats["feishu"]["in_progress"] == 1
    assert stats["feishu"]["blocked"] == 1
    assert "共 4 个任务" in result["summary"]


@pytest.mark.asyncio
async def test_generate_report_contains_blocked_details(generator, mock_projection):
    """Report content should include blocked task details."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection(
            "rec_blocked",
            title="部署服务",
            status="阻塞(Blocked)",
            blocked_reason="服务器未就绪",
        ),
    ]

    result = await generator.generate()

    assert "部署服务" in result["content"]
    assert "服务器未就绪" in result["content"]
    assert "阻塞任务" in result["content"]


@pytest.mark.asyncio
async def test_fetch_feishu_tasks_returns_analysis_snapshots(generator, mock_projection):
    """Feishu tasks should cross into reports through the Analysis projection."""
    mock_projection.list_subtask_progress.return_value = [
        _subtask_projection("rec_1", title="完成设计", status="已完成(Done)"),
    ]

    [task] = await generator._fetch_feishu_tasks()

    assert isinstance(task, AnalysisFeishuTaskSnapshot)
    assert task.record_id == "rec_1"
    assert task.title == "完成设计"
    assert task.is_completed is True


@pytest.mark.asyncio
async def test_generate_without_subtask_projection_data(mock_messenger, mock_projection):
    """Empty projection data should return an empty report."""
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    generator = DailyReportGenerator(
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    mock_projection.list_subtask_progress.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_chat_success(generator, mock_messenger):
    """Daily report push should succeed with configured chat ID."""
    result = await generator.push_to_chat("测试日报内容")

    assert result is True
    mock_messenger.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_chat_no_chat_id(mock_messenger, mock_projection):
    """Missing chat ID should make push return False."""
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    generator = DailyReportGenerator(
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    result = await generator.push_to_chat("内容")

    assert result is False


@pytest.mark.asyncio
async def test_push_to_chat_error(generator, mock_messenger):
    """Push errors should return False."""
    mock_messenger.send_message.side_effect = Exception("network error")

    result = await generator.push_to_chat("内容")

    assert result is False


def test_compute_stats_with_typed_projection(generator):
    """_compute_stats should count Feishu + projected OP rows correctly."""
    from shared.capabilities.analysis.core.domain.projection import (
        WorkPackageProjection,
    )
    from shared.capabilities.analysis.core.domain.report import (
        AnalysisReportStats,
        TaskSourceStats,
    )

    feishu_tasks = [
        _feishu_task(status="已完成(Done)"),
        _feishu_task(status="已完成(Done)"),
        _feishu_task(status="进行中(In Progress)"),
        _feishu_task(status="阻塞(Blocked)"),
        _feishu_task(status="未开始"),
        _feishu_task(status="未开始"),
    ]
    op_tasks = [
        WorkPackageProjection(
            wp_id=1,
            project_id=1,
            subject="WP done",
            type_name="Task",
            status_name="closed",
            percentage_done=100,
            assigned_to=None,
            parent_id=None,
            due_date=None,
            updated_at=datetime.now(UTC),
            extra={},
        ),
        WorkPackageProjection(
            wp_id=2,
            project_id=1,
            subject="WP active",
            type_name="Task",
            status_name="In progress",
            percentage_done=50,
            assigned_to=None,
            parent_id=None,
            due_date=None,
            updated_at=datetime.now(UTC),
            extra={},
        ),
    ]

    stats = generator._compute_stats(feishu_tasks, op_tasks)
    assert stats == AnalysisReportStats(
        feishu=TaskSourceStats(total=6, completed=2, in_progress=1, blocked=1),
        op=TaskSourceStats(total=2, completed=1, in_progress=1),
    )
    assert stats.to_legacy_dict()["total"] == 8
