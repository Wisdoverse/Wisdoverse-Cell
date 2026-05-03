"""
Unit Tests - ChatAgent

ChatAgent 的核心逻辑单元测试。
"""
from unittest.mock import MagicMock

import pytest

from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_agent_init(mock_event_bus, mock_chat_service):
    """验证 ChatAgent 初始化属性"""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)

    assert agent.agent_id == "chat-agent"
    assert agent.subscribed_events == [
        EventTypes.CHAT_PM_RESPONSE,
        EventTypes.COORDINATOR_RESPONSE,
    ]
    assert agent.published_events == [
        EventTypes.CHAT_PM_QUERY,
        EventTypes.COORDINATOR_COMMAND,
        EventTypes.SYNC_TRIGGER,
    ]


@pytest.mark.asyncio
async def test_handle_event_pm_response(mock_event_bus, mock_chat_service):
    """验证 handle_event 处理 CHAT_PM_RESPONSE 事件，返回空列表"""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)

    event = Event.create(
        event_type=EventTypes.CHAT_PM_RESPONSE,
        source_agent="pjm-agent",
        payload={"user_id": "test_user", "reply": "pm response"},
    )

    result = await agent.handle_event(event)

    assert result == []


@pytest.mark.asyncio
async def test_handle_request_chat(mock_event_bus, mock_chat_service):
    """验证 handle_request action=chat 调用 chat service"""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)
    agent._chat = mock_chat_service

    result = await agent.handle_request({
        "action": "chat",
        "message": "hello",
        "user_id": "user1",
    })

    assert result == {"reply": "mock reply"}
    mock_chat_service.chat.assert_awaited_once_with(message="hello", user_id="user1")


@pytest.mark.asyncio
async def test_handle_request_chat_user_assistant(mock_event_bus, mock_chat_service):
    """handle_request action=chat_user_assistant calls the user assistant."""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)
    agent._chat = mock_chat_service

    result = await agent.handle_request({
        "action": "chat_user_assistant",
        "message": "项目进度如何",
        "user_id": "user2",
        "user_name": "张三",
        "chat_id": "oc_abc",
        "chat_type": "group",
    })

    assert result == {"reply": "mock reply"}
    mock_chat_service.chat_with_user_assistant.assert_awaited_once_with(
        message="项目进度如何",
        user_id="user2",
        user_name="张三",
        context={
            "user_id": "user2",
            "user_name": "张三",
            "chat_id": "oc_abc",
            "chat_type": "group",
        },
    )


@pytest.mark.asyncio
async def test_handle_request_clear_history(mock_event_bus, mock_chat_service):
    """验证 handle_request action=clear_history 清除聊天历史"""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)
    agent._chat = mock_chat_service

    result = await agent.handle_request({
        "action": "clear_history",
        "user_id": "user1",
    })

    assert result == {"status": "cleared"}
    mock_chat_service.clear_history.assert_awaited_once_with("user1")


@pytest.mark.asyncio
async def test_handle_request_unknown(mock_event_bus, mock_chat_service):
    """验证 handle_request 未知 action 返回错误"""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)
    agent._chat = mock_chat_service

    result = await agent.handle_request({"action": "nonexistent"})

    assert result == {"error": "unknown action"}
