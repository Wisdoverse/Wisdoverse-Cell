"""
Unit Tests - AlertService

测试预警服务的截止日期/阻塞/进度/工作负载检测逻辑。
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_bitable():
    bitable = AsyncMock()
    bitable.list_all_records = AsyncMock(return_value=[])
    return bitable


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.get_rule = MagicMock(return_value="3")
    return config


@pytest.fixture
def alert_service(mock_bitable, mock_config):
    from agents.capabilities.project_management.core.alert_service import AlertService

    return AlertService(bitable=mock_bitable, config=mock_config)


@pytest.mark.asyncio
async def test_check_all_empty(alert_service, mock_bitable):
    """无任务时 check_all 应返回空预警列表"""
    mock_bitable.list_all_records.return_value = []

    with patch("agents.capabilities.project_management.core.alert_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        alerts = await alert_service.check_all()

    assert alerts == []


@pytest.mark.asyncio
async def test_check_deadlines_overdue(alert_service, mock_bitable):
    """逾期任务应产生 critical 级别的 deadline 预警"""
    # 3 天前的时间戳（毫秒）
    overdue_ts = int((datetime.now(UTC) - timedelta(days=3)).timestamp() * 1000)
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "部署服务", "状态": "进行中", "计划完成日期": overdue_ts}},
    ]

    with patch("agents.capabilities.project_management.core.alert_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        alerts = await alert_service.check_all()

    deadline_alerts = [a for a in alerts if a["type"] == "deadline"]
    assert len(deadline_alerts) == 1
    assert deadline_alerts[0]["severity"] == "critical"
    assert "逾期" in deadline_alerts[0]["message"]
    assert deadline_alerts[0]["task"] == "部署服务"


@pytest.mark.asyncio
async def test_check_deadlines_soon(alert_service, mock_bitable, mock_config):
    """即将到期任务（在预警天数内）应产生 warning 级别的 deadline 预警"""
    mock_config.get_rule.return_value = "3"
    # 2 天后到期
    soon_ts = int((datetime.now(UTC) + timedelta(days=2)).timestamp() * 1000)
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "编写测试", "状态": "进行中", "计划完成日期": soon_ts}},
    ]

    with patch("agents.capabilities.project_management.core.alert_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        alerts = await alert_service.check_all()

    deadline_alerts = [a for a in alerts if a["type"] == "deadline"]
    assert len(deadline_alerts) == 1
    assert deadline_alerts[0]["severity"] == "warning"
    assert "截止" in deadline_alerts[0]["message"]


@pytest.mark.asyncio
async def test_check_deadlines_completed_ignored(alert_service, mock_bitable):
    """已完成任务即使逾期也不应产生预警"""
    overdue_ts = int((datetime.now(UTC) - timedelta(days=5)).timestamp() * 1000)
    mock_bitable.list_all_records.return_value = [
        {
            "fields": {
                "任务(动宾短语)": "已完成任务",
                "状态": "已完成(Done)",
                "计划完成日期": overdue_ts,
            }
        },
    ]

    with patch("agents.capabilities.project_management.core.alert_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        alerts = await alert_service.check_all()

    deadline_alerts = [a for a in alerts if a["type"] == "deadline"]
    assert len(deadline_alerts) == 0


@pytest.mark.asyncio
async def test_check_blocked(alert_service, mock_bitable):
    """阻塞状态的任务应产生 warning 级别的 blocked 预警"""
    mock_bitable.list_all_records.return_value = [
        {
            "fields": {
                "任务(动宾短语)": "等待审批",
                "状态": "阻塞(Blocked)",
                "阻塞原因": "等待法务审核",
            }
        },
    ]

    with patch("agents.capabilities.project_management.core.alert_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        alerts = await alert_service.check_all()

    blocked_alerts = [a for a in alerts if a["type"] == "blocked"]
    assert len(blocked_alerts) == 1
    assert blocked_alerts[0]["severity"] == "warning"
    assert "等待法务审核" in blocked_alerts[0]["message"]
    assert blocked_alerts[0]["task"] == "等待审批"


@pytest.mark.asyncio
async def test_check_progress_behind(alert_service, mock_bitable, mock_config):
    """进度显著落后的任务应产生 warning 级别的 progress 预警"""
    mock_config.get_rule.side_effect = lambda name, default="": {
        "截止日期预警天数": "3",
        "进度落后阈值": "20",
    }.get(name, default)

    now = datetime.now(UTC)
    # 任务从 30 天前开始，10 天后到期 — 已过 75%+ 时间
    start_ts = int((now - timedelta(days=30)).timestamp() * 1000)
    due_ts = int((now + timedelta(days=10)).timestamp() * 1000)

    mock_bitable.list_all_records.return_value = [
        {
            "fields": {
                "任务(动宾短语)": "开发核心功能",
                "状态": "进行中",
                "开始日期": start_ts,
                "计划完成日期": due_ts,
                "进度": 10,  # 实际只有 10%，预期应在 75% 左右
            }
        },
    ]

    with patch("agents.capabilities.project_management.core.alert_service.settings") as mock_settings:
        mock_settings.feishu_pm_app_token = "token"
        mock_settings.feishu_pm_task_table_id = "table"
        alerts = await alert_service.check_all()

    progress_alerts = [a for a in alerts if a["type"] == "progress"]
    assert len(progress_alerts) == 1
    assert progress_alerts[0]["severity"] == "warning"
    assert "进度落后" in progress_alerts[0]["message"]


def test_check_workload_empty(alert_service):
    """工作负载检查（Phase 2 stub）应返回空列表"""
    result = alert_service._check_workload()
    assert result == []
