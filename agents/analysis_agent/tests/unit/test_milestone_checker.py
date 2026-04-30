"""
Unit Tests - MilestoneChecker

测试里程碑风险检查逻辑，使用 mock 的 bitable_service。
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_bitable():
    bitable = AsyncMock()
    bitable.list_all_records = AsyncMock(return_value=[])
    return bitable


@pytest.fixture
def checker(mock_bitable):
    from agents.analysis_agent.core.milestone_checker import MilestoneChecker
    return MilestoneChecker(bitable=mock_bitable)


@pytest.mark.asyncio
async def test_check_no_tasks(checker, mock_bitable):
    """无任务时应返回空风险列表"""
    mock_bitable.list_all_records.return_value = []

    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        risks = await checker.check()

    assert risks == []


@pytest.mark.asyncio
async def test_check_blocked_subtasks(checker, mock_bitable):
    """有阻塞子任务时应产生 blocked_subtasks 风险"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#2266", "状态": "阻塞(Blocked)", "任务(动宾短语)": "任务A"}},
        {"fields": {"关联 Feature ID (关键字段)": "#2266", "状态": "进行中(In Progress)", "任务(动宾短语)": "任务B"}},
    ]

    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        risks = await checker.check()

    blocked_risks = [r for r in risks if r["type"] == "blocked_subtasks"]
    assert len(blocked_risks) == 1
    assert blocked_risks[0]["severity"] == "warning"
    assert "任务A" in blocked_risks[0]["blocked_tasks"]


@pytest.mark.asyncio
async def test_check_multiple_blocked_is_critical(checker, mock_bitable):
    """多个阻塞子任务时 severity 应为 critical"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#100", "状态": "阻塞(Blocked)", "任务(动宾短语)": "A"}},
        {"fields": {"关联 Feature ID (关键字段)": "#100", "状态": "Blocked", "任务(动宾短语)": "B"}},
        {"fields": {"关联 Feature ID (关键字段)": "#100", "状态": "进行中", "任务(动宾短语)": "C"}},
    ]

    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        risks = await checker.check()

    blocked_risks = [r for r in risks if r["type"] == "blocked_subtasks"]
    assert len(blocked_risks) == 1
    assert blocked_risks[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_check_low_progress(checker, mock_bitable):
    """完成率低于 30% 时应产生 low_progress 风险"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T1"}},
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T2"}},
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T3"}},
        {"fields": {"关联 Feature ID (关键字段)": "#200", "状态": "进行中", "任务(动宾短语)": "T4"}},
    ]

    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        risks = await checker.check()

    progress_risks = [r for r in risks if r["type"] == "low_progress"]
    assert len(progress_risks) == 1
    assert "0%" in progress_risks[0]["message"]


@pytest.mark.asyncio
async def test_check_no_risk_when_all_completed(checker, mock_bitable):
    """全部完成时不应有风险"""
    mock_bitable.list_all_records.return_value = [
        {"fields": {"关联 Feature ID (关键字段)": "#300", "状态": "已完成(Done)", "任务(动宾短语)": "T1"}},
        {"fields": {"关联 Feature ID (关键字段)": "#300", "状态": "已完成(Done)", "任务(动宾短语)": "T2"}},
    ]

    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        risks = await checker.check()

    assert risks == []


@pytest.mark.asyncio
async def test_push_risks_success(checker):
    """推送风险到飞书群应成功"""
    risks = [
        {"type": "blocked_subtasks", "severity": "critical", "message": "Feature #1: 2/3 阻塞", "blocked_tasks": ["A", "B"]},
    ]

    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings, \
         patch("agents.analysis_agent.core.milestone_checker.get_feishu_client") as mock_get_client:
        mock_settings.feishu_report_chat_id = "chat_456"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        result = await checker.push_risks(risks)

    assert result is True
    mock_client.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_push_risks_empty(checker):
    """空风险列表不应推送"""
    result = await checker.push_risks([])
    assert result is False


@pytest.mark.asyncio
async def test_push_risks_no_chat_id(checker):
    """未配置 chat_id 时不应推送"""
    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_report_chat_id = ""
        result = await checker.push_risks([{"type": "test", "severity": "warning", "message": "x"}])
    assert result is False


@pytest.mark.asyncio
async def test_check_no_config(checker, mock_bitable):
    """未配置 app_token 时应返回空"""
    with patch("agents.analysis_agent.core.milestone_checker.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = ""
        mock_settings.feishu_pm_task_table_id = ""
        risks = await checker.check()

    assert risks == []
    mock_bitable.list_all_records.assert_not_called()
