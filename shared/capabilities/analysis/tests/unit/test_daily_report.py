"""
Unit Tests - DailyReportGenerator

Tests daily report generation with a mocked Bitable port.
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
def mock_op():
    op = AsyncMock()
    op.get_work_packages = AsyncMock(return_value=[])
    return op


@pytest.fixture
def mock_messenger():
    messenger = AsyncMock()
    messenger.send_message = AsyncMock(return_value={})
    return messenger


@pytest.fixture
def generator(mock_bitable, mock_messenger, mock_op):
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    return DailyReportGenerator(
        bitable=mock_bitable,
        messenger=mock_messenger,
        op_client=mock_op,
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
async def test_generate_no_config(mock_bitable, mock_messenger, mock_op):
    """Missing app token should return empty data."""
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    generator = DailyReportGenerator(
        bitable=mock_bitable,
        messenger=mock_messenger,
        op_client=mock_op,
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
async def test_push_to_chat_no_chat_id(mock_bitable, mock_messenger, mock_op):
    """Missing chat ID should make push return False."""
    from shared.capabilities.analysis.core.daily_report import DailyReportGenerator

    generator = DailyReportGenerator(
        bitable=mock_bitable,
        messenger=mock_messenger,
        op_client=mock_op,
    )
    result = await generator.push_to_chat("内容")

    assert result is False


@pytest.mark.asyncio
async def test_push_to_chat_error(generator, mock_messenger):
    """Push errors should return False."""
    mock_messenger.send_message.side_effect = Exception("network error")

    result = await generator.push_to_chat("内容")

    assert result is False


def test_compute_stats(generator):
    """_compute_stats should count each status correctly."""
    tasks = [
        {"状态": "已完成(Done)"},
        {"状态": "已完成(Done)"},
        {"状态": "进行中(In Progress)"},
        {"状态": "阻塞(Blocked)"},
        {"状态": "未开始"},
        {"状态": "未开始"},
    ]
    stats = generator._compute_stats(tasks, [])
    assert stats["total"] == 6
    assert stats["feishu"]["completed"] == 2
    assert stats["feishu"]["in_progress"] == 1
    assert stats["feishu"]["blocked"] == 1
