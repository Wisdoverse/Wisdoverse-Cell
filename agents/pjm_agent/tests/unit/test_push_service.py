"""
Unit Tests - PushService

测试推送服务的消息发送逻辑。
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def push_service():
    from agents.pjm_agent.core.push_service import PushService

    return PushService()


@pytest.mark.asyncio
async def test_push_alerts_success(push_service):
    """有预警且配置了 chat_id 时应格式化并成功发送"""
    alerts = [
        {"type": "deadline", "severity": "critical", "task": "部署服务", "message": "已逾期 3 天"},
        {
            "type": "blocked",
            "severity": "warning",
            "task": "等待审批",
            "message": "阻塞原因: 等待法务",
        },
    ]

    with (
        patch("agents.pjm_agent.core.push_service.settings") as mock_settings,
        patch("agents.pjm_agent.core.push_service.get_feishu_client") as mock_get_client,
    ):
        mock_settings.feishu_report_chat_id = "chat_pm_001"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        result = await push_service.push_alerts(alerts)

    assert result is True
    mock_client.send_message.assert_called_once()

    # 验证发送内容包含预警信息
    call_kwargs = mock_client.send_message.call_args[1]
    assert call_kwargs["receive_id"] == "chat_pm_001"
    assert call_kwargs["receive_id_type"] == "chat_id"
    assert "部署服务" in call_kwargs["content"]
    assert "等待审批" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_push_alerts_no_chat_id(push_service):
    """未配置 chat_id 时应记录 warning 并返回 False"""
    alerts = [
        {"type": "deadline", "severity": "critical", "task": "T1", "message": "已逾期"},
    ]

    with patch("agents.pjm_agent.core.push_service.settings") as mock_settings:
        mock_settings.feishu_report_chat_id = ""
        result = await push_service.push_alerts(alerts)

    assert result is False


@pytest.mark.asyncio
async def test_push_alerts_empty(push_service):
    """空预警列表应返回 False"""
    result = await push_service.push_alerts([])
    assert result is False


@pytest.mark.asyncio
async def test_push_risks_success(push_service):
    """有风险且配置了 chat_id 时应格式化并成功发送"""
    risks = [
        {"risk_level": "high", "message": "核心模块延期风险"},
        {"risk_level": "medium", "message": "人员不足风险"},
    ]

    with (
        patch("agents.pjm_agent.core.push_service.settings") as mock_settings,
        patch("agents.pjm_agent.core.push_service.get_feishu_client") as mock_get_client,
    ):
        mock_settings.feishu_report_chat_id = "chat_risk_001"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        result = await push_service.push_risks(risks)

    assert result is True
    mock_client.send_message.assert_called_once()

    call_kwargs = mock_client.send_message.call_args[1]
    assert call_kwargs["receive_id"] == "chat_risk_001"
    assert "核心模块延期风险" in call_kwargs["content"]
    assert "人员不足风险" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_push_risks_empty(push_service):
    """空风险列表应返回 False"""
    result = await push_service.push_risks([])
    assert result is False
