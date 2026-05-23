"""
Unit Tests - WeeklyReportGenerator

Tests weekly report generation with mocked Bitable + projection ports.
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
def mock_projection():
    projection = AsyncMock()
    projection.list_work_packages = AsyncMock(return_value=[])
    return projection


@pytest.fixture
def mock_messenger():
    messenger = AsyncMock()
    messenger.send_message = AsyncMock(return_value={})
    return messenger


@pytest.fixture
def generator(mock_bitable, mock_messenger, mock_projection):
    from shared.capabilities.analysis.core.weekly_report import WeeklyReportGenerator

    return WeeklyReportGenerator(
        bitable=mock_bitable,
        messenger=mock_messenger,
        projection_port=mock_projection,
        config=AnalysisCoreConfig.from_values(
            feishu_report_chat_id="chat_123",
            feishu_pm_app_token="token",
            feishu_pm_task_table_id="table",
        ),
    )


@pytest.mark.asyncio
async def test_generate_empty(generator, mock_bitable):
    """No task data should return an empty report."""
    mock_bitable.list_all_records.return_value = []

    result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    assert result["summary"] == "无数据"


@pytest.mark.asyncio
async def test_generate_with_tasks(generator, mock_bitable):
    """Task data should generate a weekly report with stats."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "完成设计", "状态": "已完成(Done)"}},
        {"fields": {"任务(动宾短语)": "开发功能A", "状态": "进行中(In Progress)"}},
        {"fields": {"任务(动宾短语)": "修复BugX", "状态": "阻塞(Blocked)", "阻塞原因": "等待API"}},
        {"fields": {"任务(动宾短语)": "编写文档", "状态": "未开始"}},
    ]

    result = await generator.generate()

    assert "共 4 个任务" in result["summary"]
    assert "完成设计" in result["content"]


@pytest.mark.asyncio
async def test_format_report_categorizes(generator):
    """_format_report should categorize completed, in-progress, and blocked tasks."""
    tasks = [
        {"任务(动宾短语)": "已完成任务", "状态": "已完成(Done)"},
        {"任务(动宾短语)": "进行中任务", "状态": "进行中(In Progress)"},
        {"任务(动宾短语)": "阻塞任务", "状态": "阻塞(Blocked)", "阻塞原因": "依赖未就绪"},
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
    from datetime import UTC, datetime

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
async def test_push_to_chat_no_chat_id(mock_bitable, mock_messenger, mock_projection):
    """Missing chat ID should make push return False."""
    from shared.capabilities.analysis.core.weekly_report import WeeklyReportGenerator

    generator = WeeklyReportGenerator(
        bitable=mock_bitable,
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    result = await generator.push_to_chat("内容")

    assert result is False
