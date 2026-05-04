"""Unit tests for dev_agent notification boundary."""
from unittest.mock import AsyncMock

import pytest

from agents.dev_agent.core.notifier import DevNotifier


@pytest.mark.asyncio
async def test_notifier_sends_through_injected_messenger() -> None:
    messenger = AsyncMock()
    messenger.send_message = AsyncMock(return_value={})
    notifier = DevNotifier(messenger=messenger, chat_id="chat_1")

    await notifier.notify_task_completed(wp_id=42, mr_url="https://gitlab.example/mr/1")

    messenger.send_message.assert_called_once()
    kwargs = messenger.send_message.call_args.kwargs
    assert kwargs["receive_id"] == "chat_1"
    assert kwargs["receive_id_type"] == "chat_id"
    assert kwargs["msg_type"] == "text"
    assert "WP#42" in kwargs["content"]


@pytest.mark.asyncio
async def test_notifier_without_messenger_is_noop() -> None:
    notifier = DevNotifier()

    await notifier.notify_task_failed(wp_id=42, error="boom")
