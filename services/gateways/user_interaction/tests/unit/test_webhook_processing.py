import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.gateways.user_interaction.core.webhook_processing import (
    WebhookMessageProcessingUseCase,
    WebhookProcessCommand,
)


def _command(*, chat_type: str = "p2p") -> WebhookProcessCommand:
    return WebhookProcessCommand(
        user_id="ou_1",
        text="hello",
        message={"message_id": "msg_1"},
        chat_type=chat_type,
        user_name="Alice",
        chat_id="oc_1",
    )


def _agent(*, result: dict | None = None, error: Exception | None = None) -> MagicMock:
    agent = MagicMock()
    if error is not None:
        agent.handle_request = AsyncMock(side_effect=error)
    else:
        agent.handle_request = AsyncMock(return_value=result or {})
    return agent


def _messenger() -> MagicMock:
    messenger = MagicMock()
    messenger.add_reaction = AsyncMock(return_value=True)
    messenger.send_message = AsyncMock(return_value="sent")
    messenger.reply_message = AsyncMock(return_value="replied")
    return messenger


@pytest.mark.asyncio
async def test_process_message_without_reply_returns_card_sent_and_normalizes_request() -> None:
    agent = _agent(result={"reply": ""})
    messenger = _messenger()
    build_reply_card = MagicMock(return_value={"kind": "reply"})

    result = await WebhookMessageProcessingUseCase().process_message(
        _command(),
        agent=agent,
        messenger=messenger,
        build_reply_card=build_reply_card,
    )

    assert result.status == "card_sent"
    assert result.elapsed >= 0
    messenger.add_reaction.assert_awaited_once_with("msg_1", "OnIt")
    agent.handle_request.assert_awaited_once_with(
        {
            "action": "chat_user_assistant",
            "message": "hello",
            "user_id": "ou_1",
            "user_name": "Alice",
            "chat_id": "oc_1",
            "chat_type": "p2p",
        }
    )
    build_reply_card.assert_not_called()
    messenger.send_message.assert_not_awaited()
    messenger.reply_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_message_sends_p2p_reply_card_to_open_id() -> None:
    agent = _agent(result={"reply": "Done"})
    messenger = _messenger()

    result = await WebhookMessageProcessingUseCase().process_message(
        _command(),
        agent=agent,
        messenger=messenger,
        build_reply_card=lambda reply, elapsed: {"reply": reply, "elapsed": elapsed},
    )

    assert result.status == "replied"
    messenger.send_message.assert_awaited_once()
    call = messenger.send_message.await_args.kwargs
    assert call["receive_id"] == "ou_1"
    assert call["receive_id_type"] == "open_id"
    assert call["msg_type"] == "interactive"
    assert json.loads(call["content"])["reply"] == "Done"
    messenger.reply_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_message_replies_to_group_message() -> None:
    agent = _agent(result={"reply": "Done"})
    messenger = _messenger()

    result = await WebhookMessageProcessingUseCase().process_message(
        _command(chat_type="group"),
        agent=agent,
        messenger=messenger,
        build_reply_card=lambda reply, elapsed: {"reply": reply, "elapsed": elapsed},
    )

    assert result.status == "replied"
    messenger.reply_message.assert_awaited_once()
    call = messenger.reply_message.await_args.kwargs
    assert call["message_id"] == "msg_1"
    assert call["msg_type"] == "interactive"
    assert json.loads(call["content"])["reply"] == "Done"
    messenger.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_message_sends_text_error_reply_when_agent_fails() -> None:
    agent = _agent(error=RuntimeError("boom"))
    messenger = _messenger()

    result = await WebhookMessageProcessingUseCase().process_message(
        _command(),
        agent=agent,
        messenger=messenger,
        build_reply_card=MagicMock(),
    )

    assert result.status == "error"
    assert result.error == "boom"
    assert result.reply_error == ""
    messenger.send_message.assert_awaited_once()
    call = messenger.send_message.await_args.kwargs
    assert call["receive_id"] == "ou_1"
    assert call["receive_id_type"] == "open_id"
    assert call["msg_type"] == "text"
    assert json.loads(call["content"]) == {
        "text": "抱歉，处理消息时出现问题，请稍后再试。"
    }
