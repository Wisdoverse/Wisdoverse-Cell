"""
Unit Tests - DailyReportGenerator

Tests daily report generation with mocked Bitable + projection ports.
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
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    return DailyReportGenerator(
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
    assert result["stats"] == {}


@pytest.mark.asyncio
async def test_generate_with_tasks(generator, mock_bitable):
    """Task data should generate a stats report."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "完成设计", "状态": "已完成(Done)"}},
        {"fields": {"任务(动宾短语)": "开发功能A", "状态": "进行中(In Progress)"}},
        {"fields": {"任务(动宾短语)": "修复BugX", "状态": "阻塞(Blocked)", "阻塞原因": "等待API"}},
        {"fields": {"任务(动宾短语)": "编写文档", "状态": "未开始"}},
    ]

    result = await generator.generate()

    stats = result["stats"]
    assert stats["total"] == 4
    assert stats["feishu"]["completed"] == 1
    assert stats["feishu"]["in_progress"] == 1
    assert stats["feishu"]["blocked"] == 1
    assert "共 4 个任务" in result["summary"]


@pytest.mark.asyncio
async def test_generate_report_contains_blocked_details(generator, mock_bitable):
    """Report content should include blocked task details."""
    mock_bitable.list_all_records.return_value = [
        {"fields": {
            "任务(动宾短语)": "部署服务",
            "状态": "阻塞(Blocked)",
            "阻塞原因": "服务器未就绪",
        }},
    ]

    result = await generator.generate()

    assert "部署服务" in result["content"]
    assert "服务器未就绪" in result["content"]
    assert "阻塞任务" in result["content"]


@pytest.mark.asyncio
async def test_generate_no_config(mock_bitable, mock_messenger, mock_projection):
    """Missing app token should return empty data."""
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    generator = DailyReportGenerator(
        bitable=mock_bitable,
        messenger=mock_messenger,
        projection_port=mock_projection,
    )
    result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    mock_bitable.list_all_records.assert_not_called()


@pytest.mark.asyncio
async def test_push_to_chat_success(generator, mock_messenger):
    """Daily report push should succeed with configured chat ID."""
    result = await generator.push_to_chat("测试日报内容")

    assert result is True
    mock_messenger.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_chat_no_chat_id(mock_bitable, mock_messenger, mock_projection):
    """Missing chat ID should make push return False."""
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    generator = DailyReportGenerator(
        bitable=mock_bitable,
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
    from datetime import UTC, datetime

    from shared.capabilities.analysis.core.domain.projection import (
        WorkPackageProjection,
    )

    feishu_tasks = [
        {"状态": "已完成(Done)"},
        {"状态": "已完成(Done)"},
        {"状态": "进行中(In Progress)"},
        {"状态": "阻塞(Blocked)"},
        {"状态": "未开始"},
        {"状态": "未开始"},
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
    assert stats["total"] == 8
    assert stats["feishu"]["completed"] == 2
    assert stats["feishu"]["in_progress"] == 1
    assert stats["feishu"]["blocked"] == 1
    assert stats["op"] == {"total": 2, "completed": 1, "in_progress": 1}
