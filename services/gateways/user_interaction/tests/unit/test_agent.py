"""
Unit Tests - ChatAgent

Core ChatAgent behavior tests.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.app import UNKNOWN_ACTION_ERROR_CODE
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
    from services.gateways.user_interaction.service.agent import ChatAgent
    from shared.observability.privacy import hash_identifier

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)

    event = Event.create(
        event_type=EventTypes.CHAT_PM_RESPONSE,
        source_agent="pjm-agent",
        payload={"user_id": "test_user", "reply": "pm response"},
    )

    with patch(
        "services.gateways.user_interaction.core.event_use_cases.logger"
    ) as logger:
        result = await agent.handle_event(event)

    assert result == []
    log_call = logger.info.call_args
    assert log_call.args == ("project_management_response_received",)
    assert log_call.kwargs["user_hash"] == hash_identifier("test_user")
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
async def test_health_check_uses_injected_health_store(mock_event_bus):
    """Health check delegates database probing to the health-store port."""
    from services.gateways.user_interaction.service.agent import ChatAgent

    health_store = AsyncMock()
    health_store.is_database_ready = AsyncMock(return_value=True)
    agent = ChatAgent(
        db=MagicMock(),
        bus=mock_event_bus,
        health_store=health_store,
    )
    agent._chat = MagicMock()

    result = await agent.health_check()

    assert result == {"database": True, "chat_service": True}
    health_store.is_database_ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_request_unknown(mock_event_bus, mock_chat_service):
    """Verify handle_request returns an error for an unknown action."""
    from services.gateways.user_interaction.service.agent import ChatAgent

    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus)
    agent._chat = mock_chat_service

    result = await agent.handle_request({"action": "nonexistent"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }


@pytest.mark.asyncio
async def test_cleanup_conversations_uses_history_store(mock_event_bus):
    """cleanup_conversations delegates persistence to the chat history store."""
    from services.gateways.user_interaction.service.agent import ChatAgent

    history_store = MagicMock()
    history_store.delete_inactive = AsyncMock(return_value=7)
    agent = ChatAgent(db=MagicMock(), bus=mock_event_bus, history_store=history_store)

    result = await agent.handle_request({"action": "cleanup_conversations"})

    assert result == {"status": "ok", "deleted": 7}
    history_store.delete_inactive.assert_awaited_once_with(days=30)
