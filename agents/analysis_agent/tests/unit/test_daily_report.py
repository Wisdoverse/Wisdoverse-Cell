"""
Unit Tests - DailyReportGenerator

测试日报生成逻辑，使用 mock 的 bitable_service。
"""
from unittest.mock import AsyncMock, patch

import pytest


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
def generator(mock_bitable, mock_op):
    from agents.analysis_agent.core.daily_report import DailyReportGenerator
    return DailyReportGenerator(bitable=mock_bitable, op_client=mock_op)


@pytest.mark.asyncio
async def test_generate_empty(generator, mock_bitable):
    """无任务数据时应返回空报告"""
    mock_bitable.list_all_records.return_value = []

    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    assert result["summary"] == "无数据"
    assert result["stats"] == {}


@pytest.mark.asyncio
async def test_generate_with_tasks(generator, mock_bitable):
    """有任务数据时应生成统计报告"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "完成设计", "状态": "已完成(Done)"}},
        {"fields": {"任务(动宾短语)": "开发功能A", "状态": "进行中(In Progress)"}},
        {"fields": {"任务(动宾短语)": "修复BugX", "状态": "阻塞(Blocked)", "阻塞原因": "等待API"}},
        {"fields": {"任务(动宾短语)": "编写文档", "状态": "未开始"}},
    ]

    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await generator.generate()

    stats = result["stats"]
    assert stats["total"] == 4
    assert stats["feishu"]["completed"] == 1
    assert stats["feishu"]["in_progress"] == 1
    assert stats["feishu"]["blocked"] == 1
    assert "共 4 个任务" in result["summary"]


@pytest.mark.asyncio
async def test_generate_report_contains_blocked_details(generator, mock_bitable):
    """报告内容应包含阻塞任务详情"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {
            "任务(动宾短语)": "部署服务",
            "状态": "阻塞(Blocked)",
            "阻塞原因": "服务器未就绪",
        }},
    ]

    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await generator.generate()

    assert "部署服务" in result["content"]
    assert "服务器未就绪" in result["content"]
    assert "阻塞任务" in result["content"]


@pytest.mark.asyncio
async def test_generate_no_config(generator, mock_bitable):
    """未配置 app_token 时应返回空"""
    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = ""
        mock_settings.feishu_pm_task_table_id = ""
        result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    mock_bitable.list_all_records.assert_not_called()


@pytest.mark.asyncio
async def test_push_to_chat_success(generator):
    """推送日报到飞书群应成功"""
    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings, \
         patch("agents.analysis_agent.core.daily_report.get_feishu_client") as mock_get_client:
        mock_settings.feishu_report_chat_id = "chat_123"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        result = await generator.push_to_chat("测试日报内容")

    assert result is True
    mock_client.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_chat_no_chat_id(generator):
    """未配置 chat_id 时推送应返回 False"""
    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings:
        mock_settings.feishu_report_chat_id = ""
        result = await generator.push_to_chat("内容")

    assert result is False


@pytest.mark.asyncio
async def test_push_to_chat_error(generator):
    """推送失败时应返回 False"""
    with patch("agents.analysis_agent.core.daily_report.settings") as mock_settings, \
         patch("agents.analysis_agent.core.daily_report.get_feishu_client") as mock_get_client:
        mock_settings.feishu_report_chat_id = "chat_123"
        mock_client = AsyncMock()
        mock_client.send_message.side_effect = Exception("network error")
        mock_get_client.return_value = mock_client

        result = await generator.push_to_chat("内容")

    assert result is False


def test_compute_stats(generator):
    """_compute_stats 应正确统计各状态"""
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
