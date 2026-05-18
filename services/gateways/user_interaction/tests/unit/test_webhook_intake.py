from unittest.mock import AsyncMock

import pytest

from services.gateways.user_interaction.core.webhook_intake import (
    FeishuWebhookIntakeUseCase,
    user_info_cache_key,
)


def test_extract_message_event_and_mentions_text() -> None:
    intake = FeishuWebhookIntakeUseCase()
    message = intake.extract_message_event(
        {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_1"}},
                "message": {
                    "message_id": "msg_1",
                    "message_type": "text",
                    "chat_type": "group",
                    "chat_id": "oc_1",
                    "content": '{"text": "@bot hello"}',
                },
            },
        }
    )

    assert message is not None
    assert message.msg_id == "msg_1"
    assert message.chat_id == "oc_1"
    assert message.user_id == "ou_1"
    assert intake.extract_text(message) == "hello"


def test_extract_message_event_ignores_non_message_event() -> None:
    intake = FeishuWebhookIntakeUseCase()

    result = intake.extract_message_event(
        {
            "header": {"event_type": "im.chat.member.bot.added_v1"},
            "event": {},
        }
    )

    assert result is None


@pytest.mark.asyncio
async def test_is_duplicate_uses_cache_nx_ttl() -> None:
    cache = AsyncMock()
    cache.set = AsyncMock(return_value=None)

    result = await FeishuWebhookIntakeUseCase().is_duplicate("msg_1", cache)

    assert result is True
    cache.set.assert_awaited_once_with(
        "chat:dedup:msg_1",
        "1",
        nx=True,
        ex=300,
    )


@pytest.mark.asyncio
async def test_resolve_user_name_reads_cache_before_feishu_lookup() -> None:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value="Alice")
    directory = AsyncMock()

    result = await FeishuWebhookIntakeUseCase().resolve_user_name(
        "ou_1",
        cache=cache,
        user_directory=directory,
    )

    assert result == "Alice"
    cache.get.assert_awaited_once_with(user_info_cache_key("ou_1"))
    directory.get_user_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_user_name_caches_feishu_lookup() -> None:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.setex = AsyncMock()
    directory = AsyncMock()
    directory.get_user_info = AsyncMock(return_value={"name": "Alice"})

    result = await FeishuWebhookIntakeUseCase().resolve_user_name(
        "ou_1",
        cache=cache,
        user_directory=directory,
    )

    assert result == "Alice"
    directory.get_user_info.assert_awaited_once_with("ou_1")
    cache.setex.assert_awaited_once_with(user_info_cache_key("ou_1"), 3600, "Alice")
