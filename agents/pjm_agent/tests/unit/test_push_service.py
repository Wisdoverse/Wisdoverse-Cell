"""
Unit Tests - PushService

Tests PM notification formatting and sending.
"""

from unittest.mock import AsyncMock

import pytest

from agents.pjm_agent.core.config import PJMCoreConfig
from agents.pjm_agent.core.push_service import PushService


@pytest.fixture
def messenger():
    client = AsyncMock()
    client.send_message = AsyncMock()
    return client


def make_push_service(messenger, *, chat_id: str = "") -> PushService:
    return PushService(
        messenger,
        config=PJMCoreConfig.from_values(feishu_report_chat_id=chat_id),
    )


@pytest.mark.asyncio
async def test_push_alerts_success(messenger):
    """Alerts are formatted and sent when chat_id is configured."""
    push_service = make_push_service(messenger, chat_id="feishu_report_001")
    alerts = [
        {"type": "deadline", "severity": "critical", "task": "部署服务", "message": "已逾期 3 天"},
        {
            "type": "blocked",
            "severity": "warning",
            "task": "等待审批",
            "message": "阻塞原因: 等待法务",
        },
    ]

    result = await push_service.push_alerts(alerts)

    assert result is True
    messenger.send_message.assert_called_once()

    call_kwargs = messenger.send_message.call_args[1]
    assert call_kwargs["receive_id"] == "feishu_report_001"
    assert call_kwargs["receive_id_type"] == "chat_id"
    assert "部署服务" in call_kwargs["content"]
    assert "等待审批" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_push_alerts_no_chat_id(messenger):
    """Missing chat_id returns False."""
    push_service = make_push_service(messenger)
    alerts = [
        {"type": "deadline", "severity": "critical", "task": "T1", "message": "已逾期"},
    ]

    result = await push_service.push_alerts(alerts)

    assert result is False


@pytest.mark.asyncio
async def test_push_alerts_empty(messenger):
    """Empty alert lists return False."""
    push_service = make_push_service(messenger)
    result = await push_service.push_alerts([])
    assert result is False


@pytest.mark.asyncio
async def test_push_risks_success(messenger):
    """Risks are formatted and sent when chat_id is configured."""
    push_service = make_push_service(messenger, chat_id="chat_risk_001")
    risks = [
        {"risk_level": "high", "message": "核心模块延期风险"},
        {"risk_level": "medium", "message": "人员不足风险"},
    ]

    result = await push_service.push_risks(risks)

    assert result is True
    messenger.send_message.assert_called_once()

    call_kwargs = messenger.send_message.call_args[1]
    assert call_kwargs["receive_id"] == "chat_risk_001"
    assert "核心模块延期风险" in call_kwargs["content"]
    assert "人员不足风险" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_push_risks_empty(messenger):
    """Empty risk lists return False."""
    push_service = make_push_service(messenger)
    result = await push_service.push_risks([])
    assert result is False
