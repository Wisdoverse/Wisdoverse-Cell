"""
Tests for OpenClawPlatformAdapter

Tests:
1. parse_message — converts OpenClaw events to UnifiedMessage
2. parse_action — converts OpenClaw callbacks to UnifiedAction
3. send_text / send_card / update_card — RPC calls via client
4. get_user_email / get_user_name — user info lookup with caching
5. Edge cases — missing fields, invalid data
"""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from shared.integrations.openclaw.client import OpenClawClient
from shared.integrations.openclaw.platform_adapter import OpenClawPlatformAdapter
from shared.messaging.inbound.models import (
    CardAction,
    CardActionStyle,
    MessageType,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)
from shared.models.platform import Platform


@pytest.fixture
def mock_client() -> OpenClawClient:
    """Create a OpenClawClient with mocked send_request."""
    client = OpenClawClient.__new__(OpenClawClient)
    client._connected = True
    client.send_request = AsyncMock(return_value={})
    return client


@pytest.fixture
def adapter(mock_client: OpenClawClient) -> OpenClawPlatformAdapter:
    """Create adapter with mock client."""
    return OpenClawPlatformAdapter(mock_client)


def _make_raw_message(**overrides: object) -> dict:
    """Helper to build a raw OpenClaw message event."""
    base = {
        "message_id": "msg_001",
        "channel": "whatsapp",
        "chat_id": "chat_123",
        "chat_type": "private",
        "sender": {"id": "user_456", "name": "Alice"},
        "content": "Hello from OpenClaw",
        "message_type": "text",
        "timestamp": 1706500000,
        "mentions": [],
        "attachments": [],
    }
    base.update(overrides)
    return base


class TestPlatformProperty:
    """Test platform identity."""

    def test_platform_is_openclaw(self, adapter: OpenClawPlatformAdapter) -> None:
        assert adapter.platform == Platform.OPENCLAW


class TestParseMessage:
    """Test inbound message conversion."""

    @pytest.mark.asyncio
    async def test_text_message(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = _make_raw_message()
        result = await adapter.parse_message(raw)

        assert result is not None
        assert isinstance(result, UnifiedMessage)
        assert result.platform == Platform.OPENCLAW
        assert result.message_id == "msg_001"
        assert result.chat_id == "chat_123"
        assert result.chat_type == "private"
        assert result.sender_id == "user_456"
        assert result.sender_name == "Alice"
        assert result.content == "Hello from OpenClaw"
        assert result.message_type == MessageType.TEXT
        assert result.raw_data == raw

    @pytest.mark.asyncio
    async def test_image_message(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = _make_raw_message(message_type="image", content="[image]")
        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.message_type == MessageType.IMAGE

    @pytest.mark.asyncio
    async def test_file_message(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = _make_raw_message(message_type="file", content="report.pdf")
        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.message_type == MessageType.FILE

    @pytest.mark.asyncio
    async def test_rich_text_message(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = _make_raw_message(message_type="rich_text")
        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.message_type == MessageType.POST

    @pytest.mark.asyncio
    async def test_unknown_type_defaults_to_text(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        raw = _make_raw_message(message_type="sticker")
        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.message_type == MessageType.TEXT

    @pytest.mark.asyncio
    async def test_group_chat(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = _make_raw_message(chat_type="group")
        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.chat_type == "group"

    @pytest.mark.asyncio
    async def test_timestamp_conversion(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = _make_raw_message(timestamp=1706500000)
        result = await adapter.parse_message(raw)

        assert result is not None
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_missing_timestamp_uses_now(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        raw = _make_raw_message()
        del raw["timestamp"]
        result = await adapter.parse_message(raw)

        assert result is not None
        assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_missing_message_id_returns_none(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        raw = _make_raw_message()
        del raw["message_id"]
        result = await adapter.parse_message(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_sender_id_returns_none(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        raw = _make_raw_message(sender={"name": "NoId"})
        result = await adapter.parse_message(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_event_returns_none(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        result = await adapter.parse_message({})
        assert result is None

    @pytest.mark.asyncio
    async def test_mentions_and_attachments_preserved(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        raw = _make_raw_message(
            mentions=["user_1", "user_2"],
            attachments=[{"type": "image", "url": "https://example.com/img.png"}],
        )
        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.mentions == ["user_1", "user_2"]
        assert len(result.attachments) == 1


class TestParseAction:
    """Test callback conversion."""

    @pytest.mark.asyncio
    async def test_valid_action(self, adapter: OpenClawPlatformAdapter) -> None:
        raw = {
            "action_id": "approve",
            "message_id": "msg_001",
            "operator": {"id": "user_456"},
            "value": {"requirement_id": "req_789"},
        }
        result = await adapter.parse_action(raw)

        assert result is not None
        assert isinstance(result, UnifiedAction)
        assert result.platform == Platform.OPENCLAW
        assert result.action_id == "approve"
        assert result.message_id == "msg_001"
        assert result.operator_id == "user_456"
        assert result.value == {"requirement_id": "req_789"}

    @pytest.mark.asyncio
    async def test_missing_action_id_returns_none(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        raw = {"message_id": "msg_001", "operator": {"id": "user_456"}}
        result = await adapter.parse_action(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_callback_returns_none(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        result = await adapter.parse_action({})
        assert result is None


class TestSendText:
    """Test outbound text messages."""

    @pytest.mark.asyncio
    async def test_send_text(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"message_id": "sent_001"}
        )

        msg_id = await adapter.send_text("chat_123", "Hello!")

        assert msg_id == "sent_001"
        adapter._client.send_request.assert_called_once_with(
            "channel.sendText",
            params={"chat_id": "chat_123", "text": "Hello!"},
        )


class TestSendCard:
    """Test outbound card messages."""

    @pytest.mark.asyncio
    async def test_send_card(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"message_id": "sent_002"}
        )
        card = UnifiedCard(
            title="Test",
            content="Content here",
            status="Pending",
            status_color="orange",
            fields=[{"label": "Type", "value": "Feature"}],
            actions=[
                CardAction(
                    label="Approve",
                    action_id="approve",
                    style=CardActionStyle.PRIMARY,
                    value={"id": "1"},
                )
            ],
            context={"trace_id": "t_001"},
        )

        msg_id = await adapter.send_card("chat_123", card)

        assert msg_id == "sent_002"
        call_args = adapter._client.send_request.call_args
        assert call_args[0][0] == "channel.sendCard"
        params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][1]
        openclaw_card = params["card"]
        assert openclaw_card["title"] == "Test"
        assert openclaw_card["content"] == "Content here"
        assert openclaw_card["status"] == "Pending"
        assert openclaw_card["status_color"] == "orange"
        assert len(openclaw_card["actions"]) == 1
        assert openclaw_card["actions"][0]["action_id"] == "approve"
        assert openclaw_card["actions"][0]["style"] == "primary"
        assert openclaw_card["context"] == {"trace_id": "t_001"}

    @pytest.mark.asyncio
    async def test_send_minimal_card(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"message_id": "sent_003"}
        )
        card = UnifiedCard(title="Simple", content="Just text")

        msg_id = await adapter.send_card("chat_123", card)

        assert msg_id == "sent_003"
        call_args = adapter._client.send_request.call_args
        params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][1]
        openclaw_card = params["card"]
        assert "status" not in openclaw_card
        assert "actions" not in openclaw_card


class TestUpdateCard:
    """Test card updates."""

    @pytest.mark.asyncio
    async def test_update_card_success(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(return_value={"success": True})
        card = UnifiedCard(title="Updated", content="New content")

        result = await adapter.update_card("msg_001", card)

        assert result is True
        adapter._client.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_card_failure(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(return_value={"success": False})
        card = UnifiedCard(title="Updated", content="New content")

        result = await adapter.update_card("msg_001", card)

        assert result is False


class TestUserInfo:
    """Test user identity lookup."""

    @pytest.mark.asyncio
    async def test_get_user_email(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"email": "alice@example.com", "name": "Alice"}
        )

        email = await adapter.get_user_email("user_456")

        assert email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_get_user_name(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"email": "alice@example.com", "name": "Alice"}
        )

        name = await adapter.get_user_name("user_456")

        assert name == "Alice"

    @pytest.mark.asyncio
    async def test_user_info_cached(self, adapter: OpenClawPlatformAdapter) -> None:
        adapter._client.send_request = AsyncMock(
            return_value={"email": "alice@example.com", "name": "Alice"}
        )

        await adapter.get_user_email("user_456")
        await adapter.get_user_name("user_456")

        # Only one RPC call due to caching
        adapter._client.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_info_rpc_failure_returns_none(
        self, adapter: OpenClawPlatformAdapter
    ) -> None:
        adapter._client.send_request = AsyncMock(side_effect=RuntimeError("RPC error"))

        email = await adapter.get_user_email("user_456")
        name = await adapter.get_user_name("user_456")

        assert email is None
        assert name is None


class TestAdapterInheritance:
    """Test that adapter follows BasePlatformAdapter contract."""

    def test_is_instance_of_base(self, adapter: OpenClawPlatformAdapter) -> None:
        from shared.messaging.inbound.adapter import BasePlatformAdapter

        assert isinstance(adapter, BasePlatformAdapter)

    def test_is_subclass_of_base(self) -> None:
        from shared.messaging.inbound.adapter import BasePlatformAdapter

        assert issubclass(OpenClawPlatformAdapter, BasePlatformAdapter)
