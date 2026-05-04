"""
Unit Tests - ChatAgent

Core ChatAgent behavior tests.
"""
from unittest.mock import MagicMock, patch

import pytest

from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_agent_init(mock_event_bus, mock_chat_service):
    """Verify ChatAgent initialization attributes."""
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
    """Verify handle_event processes CHAT_PM_RESPONSE and returns no events."""
    from services.gateways.user_interaction.service.agent import ChatAgent, _hash_user_id

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)

    event = Event.create(
        event_type=EventTypes.CHAT_PM_RESPONSE,
        source_agent="pjm-agent",
        payload={"user_id": "test_user", "reply": "pm response"},
    )

    with patch("services.gateways.user_interaction.service.agent.logger") as logger:
        result = await agent.handle_event(event)

    assert result == []
    log_call = logger.info.call_args
    assert log_call.args == ("project_management_response_received",)
    assert log_call.kwargs["user_hash"] == _hash_user_id("test_user")
    assert "user_id" not in log_call.kwargs


@pytest.mark.asyncio
async def test_handle_request_chat(mock_event_bus, mock_chat_service):
    """Verify handle_request action=chat calls the chat service."""
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
    """Verify handle_request action=clear_history clears chat history."""
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
    """Verify handle_request returns an error for an unknown action."""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)
    agent._chat = mock_chat_service

    result = await agent.handle_request({"action": "nonexistent"})

    assert result == {"error": "unknown action"}
