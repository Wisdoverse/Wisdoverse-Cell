"""
PlatformAdapterContract — base test suite all adapters must pass.

Each adapter provides fixtures via conftest.py:
- adapter: the adapter instance (with mock client)
- valid_message_event: a raw event dict the adapter can parse
- valid_action_event: a raw callback dict the adapter can parse
- test_chat_id: a chat_id string to send messages to
"""
import pytest

from shared.messaging.inbound.adapter import BasePlatformAdapter
from shared.messaging.inbound.models import (
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)


class PlatformAdapterContract:
    """Contract tests every PlatformAdapter must pass."""

    # -- Interface completeness --

    def test_is_subclass_of_base(self, adapter):
        assert isinstance(adapter, BasePlatformAdapter)

    def test_platform_returns_enum(self, adapter):
        assert isinstance(adapter.platform, Platform)

    # -- parse_message --

    @pytest.mark.asyncio
    async def test_parse_valid_message(self, adapter, valid_message_event):
        result = await adapter.parse_message(valid_message_event)
        assert isinstance(result, UnifiedMessage)
        assert result.message_id
        assert result.chat_id
        assert result.sender_id

    @pytest.mark.asyncio
    async def test_parse_empty_event_returns_none(self, adapter):
        result = await adapter.parse_message({})
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_none_values_no_crash(self, adapter):
        result = await adapter.parse_message({"message": None})
        assert result is None

    # -- parse_action --

    @pytest.mark.asyncio
    async def test_parse_action_returns_action_or_none(self, adapter, valid_action_event):
        result = await adapter.parse_action(valid_action_event)
        assert result is None or isinstance(result, UnifiedAction)

    @pytest.mark.asyncio
    async def test_parse_action_empty_returns_none(self, adapter):
        result = await adapter.parse_action({})
        assert result is None

    # -- send_card --

    @pytest.mark.asyncio
    async def test_send_card_returns_message_id(self, adapter, test_chat_id):
        card = UnifiedCard(title="Test", content="body")
        result = await adapter.send_card(test_chat_id, card)
        assert isinstance(result, str)
        assert len(result) > 0

    # -- send_text --

    @pytest.mark.asyncio
    async def test_send_text_returns_message_id(self, adapter, test_chat_id):
        result = await adapter.send_text(test_chat_id, "hello")
        assert isinstance(result, str)
        assert len(result) > 0

    # -- update_card --

    @pytest.mark.asyncio
    async def test_update_card_returns_bool(self, adapter):
        card = UnifiedCard(title="Updated", content="new body")
        result = await adapter.update_card("msg_test_update_001", card)
        assert isinstance(result, bool)

    # -- get_user_email --

    @pytest.mark.asyncio
    async def test_get_user_email_returns_str_or_none(self, adapter):
        result = await adapter.get_user_email("test_user_id")
        assert result is None or isinstance(result, str)

    # -- get_user_name --

    @pytest.mark.asyncio
    async def test_get_user_name_returns_str_or_none(self, adapter):
        result = await adapter.get_user_name("test_user_id")
        assert result is None or isinstance(result, str)

    # -- PII safety --

    @pytest.mark.asyncio
    async def test_raw_data_excluded_from_dump(self, adapter, valid_message_event):
        msg = await adapter.parse_message(valid_message_event)
        if msg is None:
            pytest.skip("Adapter returned None for valid event")
        dumped = msg.model_dump()
        assert "raw_data" not in dumped
