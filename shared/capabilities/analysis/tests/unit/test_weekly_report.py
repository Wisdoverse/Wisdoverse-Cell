"""
Unit Tests - WeeklyReportGenerator

Tests weekly report generation with mocked projection ports.
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
    title: str,
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
    title: str,
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
    from shared.capabilities.analysis.core.weekly_report import WeeklyReportGenerator

    return WeeklyReportGenerator(
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


@pytest.mark.asyncio
async def test_generate_with_tasks(generator, mock_projection):
    """Task data should generate a weekly report with stats."""
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

    assert "共 4 个任务" in result["summary"]
    assert "完成设计" in result["content"]


@pytest.mark.asyncio
async def test_format_report_categorizes(generator):
    """_format_report should categorize completed, in-progress, and blocked tasks."""
    tasks = [
        _feishu_task(title="已完成任务", status="已完成(Done)"),
        _feishu_task(title="进行中任务", status="进行中(In Progress)"),
        _feishu_task(
            title="阻塞任务",
            status="阻塞(Blocked)",
            blocked_reason="依赖未就绪",
        ),
    ]

    content = generator._format_report(tasks, [])

    # Verify category headings.
    assert "飞书本周完成" in content
    assert "进行中 1 个" in content  # In-progress appears only in the summary line.
    assert "阻塞中（飞书）" in content
    # Verify task names appear in their categories.
    assert "已完成任务" in content
    assert "阻塞任务" in content
    assert "依赖未就绪" in content


@pytest.mark.asyncio
async def test_format_report_includes_projected_op_completed(generator):
    """OP completion section should list projected work-package subjects."""
    from shared.capabilities.analysis.core.domain.projection import (
        WorkPackageProjection,
    )

    op_tasks = [
        WorkPackageProjection(
            wp_id=42,
            project_id=1,
            subject="项目完成里程碑",
            type_name="Milestone",
            status_name="closed",
            percentage_done=100,
            assigned_to=None,
            parent_id=None,
            due_date=None,
            updated_at=datetime.now(UTC),
            extra={},
        ),
    ]

    content = generator._format_report([], op_tasks)

    assert "OP 本周完成" in content
    assert "项目完成里程碑" in content


@pytest.mark.asyncio
async def test_push_to_chat_success(generator, mock_messenger):
    """Weekly report push should succeed with configured chat ID."""
    result = await generator.push_to_chat("测试周报内容")

    assert result is True
    mock_messenger.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_chat_no_chat_id(mock_messenger, mock_projection):
    """Missing chat ID should make push return False."""
    from shared.capabilities.analysis.core.weekly_report import WeeklyReportGenerator

    generator = WeeklyReportGenerator(
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    result = await generator.push_to_chat("内容")

    assert result is False
