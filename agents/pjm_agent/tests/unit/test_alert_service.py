"""
Unit Tests - AlertService

Tests deadline, blocked, progress, and workload alert detection.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.pjm_agent.core.config import PJMCoreConfig


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
    from agents.pjm_agent.core.alert_service import AlertService

    return AlertService(
        bitable=mock_bitable,
        config=mock_config,
        core_config=PJMCoreConfig.from_values(
            feishu_pm_app_token="token",
            feishu_pm_task_table_id="table",
        ),
    )


@pytest.mark.asyncio
async def test_check_all_empty(alert_service, mock_bitable):
    """check_all returns no alerts when there are no tasks."""
    mock_bitable.list_all_records.return_value = []

    alerts = await alert_service.check_all()

    assert alerts == []


@pytest.mark.asyncio
async def test_check_deadlines_overdue(alert_service, mock_bitable):
    """Overdue tasks produce critical deadline alerts."""
    overdue_ts = int((datetime.now(UTC) - timedelta(days=3)).timestamp() * 1000)
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "部署服务", "状态": "进行中", "计划完成日期": overdue_ts}},
    ]

    alerts = await alert_service.check_all()

    deadline_alerts = [a for a in alerts if a["type"] == "deadline"]
    assert len(deadline_alerts) == 1
    assert deadline_alerts[0]["severity"] == "critical"
    assert "逾期" in deadline_alerts[0]["message"]
    assert deadline_alerts[0]["task"] == "部署服务"


@pytest.mark.asyncio
async def test_check_deadlines_soon(alert_service, mock_bitable, mock_config):
    """Tasks due within the warning window produce warning deadline alerts."""
    mock_config.get_rule.return_value = "3"
    soon_ts = int((datetime.now(UTC) + timedelta(days=2)).timestamp() * 1000)
    mock_bitable.list_all_records.return_value = [
        {"fields": {"任务(动宾短语)": "编写测试", "状态": "进行中", "计划完成日期": soon_ts}},
    ]

    alerts = await alert_service.check_all()

    deadline_alerts = [a for a in alerts if a["type"] == "deadline"]
    assert len(deadline_alerts) == 1
    assert deadline_alerts[0]["severity"] == "warning"
    assert "截止" in deadline_alerts[0]["message"]


@pytest.mark.asyncio
async def test_check_deadlines_completed_ignored(alert_service, mock_bitable):
    """Completed tasks do not produce alerts even when overdue."""
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

    alerts = await alert_service.check_all()

    deadline_alerts = [a for a in alerts if a["type"] == "deadline"]
    assert len(deadline_alerts) == 0


@pytest.mark.asyncio
async def test_check_blocked(alert_service, mock_bitable):
    """Blocked tasks produce warning blocked alerts."""
    mock_bitable.list_all_records.return_value = [
        {
            "fields": {
                "任务(动宾短语)": "等待审批",
                "状态": "阻塞(Blocked)",
                "阻塞原因": "等待法务审核",
            }
        },
    ]

    alerts = await alert_service.check_all()

    blocked_alerts = [a for a in alerts if a["type"] == "blocked"]
    assert len(blocked_alerts) == 1
    assert blocked_alerts[0]["severity"] == "warning"
    assert "等待法务审核" in blocked_alerts[0]["message"]
    assert blocked_alerts[0]["task"] == "等待审批"


@pytest.mark.asyncio
async def test_check_progress_behind(alert_service, mock_bitable, mock_config):
    """Tasks with progress significantly behind expectations produce progress alerts."""
    mock_config.get_rule.side_effect = lambda name, default="": {
        "截止日期预警天数": "3",
        "进度落后阈值": "20",
    }.get(name, default)

    now = datetime.now(UTC)
    start_ts = int((now - timedelta(days=30)).timestamp() * 1000)
    due_ts = int((now + timedelta(days=10)).timestamp() * 1000)

    mock_bitable.list_all_records.return_value = [
        {
            "fields": {
                "任务(动宾短语)": "开发核心功能",
                "状态": "进行中",
                "开始日期": start_ts,
                "计划完成日期": due_ts,
                "进度": 10,
            }
        },
    ]

    alerts = await alert_service.check_all()

    progress_alerts = [a for a in alerts if a["type"] == "progress"]
    assert len(progress_alerts) == 1
    assert progress_alerts[0]["severity"] == "warning"
    assert "进度落后" in progress_alerts[0]["message"]


def test_check_workload_empty(alert_service):
    """Workload check returns no alerts without explicit task estimates."""
    result = alert_service._check_workload([])
    assert result == []


def test_check_workload_warns_on_explicit_estimate_over_threshold(alert_service, mock_config):
    """Workload check groups active estimated hours by assignee."""
    mock_config.get_rule.side_effect = lambda name, default="": {
        "成员工作负载预警工时": "16",
        "成员工作负载严重工时": "40",
    }.get(name, default)
    tasks = [
        {
            "任务(动宾短语)": "Build API",
            "状态": "进行中",
            "DRI (负责人)": [{"name": "Alice"}],
            "预估工时": 10,
        },
        {
            "任务(动宾短语)": "Write tests",
            "状态": "未开始",
            "DRI (负责人)": [{"name": "Alice"}],
            "预计工时": "8h",
        },
        {
            "任务(动宾短语)": "Completed",
            "状态": "已完成(Done)",
            "DRI (负责人)": [{"name": "Alice"}],
            "预估工时": 30,
        },
    ]

    result = alert_service._check_workload(tasks)

    assert result == [
        {
            "type": "overload",
            "severity": "warning",
            "task": "Alice",
            "message": "Alice workload is 18h",
            "workload_hours": 18.0,
        }
    ]


def test_check_workload_uses_critical_threshold(alert_service, mock_config):
    """Workload check escalates when estimated active hours are severe."""
    mock_config.get_rule.side_effect = lambda name, default="": {
        "成员工作负载预警工时": "16",
        "成员工作负载严重工时": "24",
    }.get(name, default)
    tasks = [
        {
            "状态": "进行中",
            "负责人": "Bob",
            "estimated_hours": 30,
        }
    ]

    result = alert_service._check_workload(tasks)

    assert result[0]["severity"] == "critical"
    assert result[0]["workload_hours"] == 30.0
