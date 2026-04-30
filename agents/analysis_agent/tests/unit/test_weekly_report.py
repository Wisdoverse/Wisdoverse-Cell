"""
Unit Tests - WeeklyReportGenerator

测试周报生成逻辑，使用 mock 的 bitable_service。
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
    from agents.analysis_agent.core.weekly_report import WeeklyReportGenerator
    return WeeklyReportGenerator(bitable=mock_bitable, op_client=mock_op)


@pytest.mark.asyncio
async def test_generate_empty(generator, mock_bitable):
    """无任务数据时应返回空报告"""
    mock_bitable.list_all_records.return_value = []

    with patch("agents.analysis_agent.core.weekly_report.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await generator.generate()

    assert result["content"] == "暂无任务数据"
    assert result["summary"] == "无数据"


@pytest.mark.asyncio
async def test_generate_with_tasks(generator, mock_bitable):
    """有任务数据时应生成包含统计的周报"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "完成设计", "状态": "已完成(Done)"}},
        {"fields": {"任务(动宾短语)": "开发功能A", "状态": "进行中(In Progress)"}},
        {"fields": {"任务(动宾短语)": "修复BugX", "状态": "阻塞(Blocked)", "阻塞原因": "等待API"}},
        {"fields": {"任务(动宾短语)": "编写文档", "状态": "未开始"}},
    ]

    with patch("agents.analysis_agent.core.weekly_report.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        result = await generator.generate()

    assert "共 4 个任务" in result["summary"]
    assert "完成设计" in result["content"]


@pytest.mark.asyncio
async def test_format_report_categorizes(generator):
    """_format_report 应按完成/进行中/阻塞分类"""
    tasks = [
        {"任务(动宾短语)": "已完成任务", "状态": "已完成(Done)"},
        {"任务(动宾短语)": "进行中任务", "状态": "进行中(In Progress)"},
        {"任务(动宾短语)": "阻塞任务", "状态": "阻塞(Blocked)", "阻塞原因": "依赖未就绪"},
    ]

    content = generator._format_report(tasks, [])

    # 验证各分类标题存在
    assert "飞书本周完成" in content
    assert "进行中 1 个" in content  # 进行中只出现在统计摘要行
    assert "阻塞中（飞书）" in content
    # 验证任务名出现在对应分类中
    assert "已完成任务" in content
    assert "阻塞任务" in content
    assert "依赖未就绪" in content


@pytest.mark.asyncio
async def test_push_to_chat_success(generator):
    """成功推送周报到飞书群应返回 True"""
    with patch("agents.analysis_agent.core.weekly_report.settings") as mock_settings, \
         patch("agents.analysis_agent.core.weekly_report.get_feishu_client") as mock_get_client:
        mock_settings.feishu_report_chat_id = "chat_123"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        result = await generator.push_to_chat("测试周报内容")

    assert result is True
    mock_client.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_chat_no_chat_id(generator):
    """未配置 chat_id 时推送应返回 False"""
    with patch("agents.analysis_agent.core.weekly_report.settings") as mock_settings:
        mock_settings.feishu_report_chat_id = ""
        result = await generator.push_to_chat("内容")

    assert result is False
