# shared/integrations/wecom/tests/test_platform_adapter.py
"""
Tests for WecomPlatformAdapter - 企微平台适配器测试
"""
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from shared.integrations.wecom.platform_adapter import WecomPlatformAdapter
from shared.messaging.inbound import (
    CardAction,
    CardActionStyle,
    MessageType,
    Platform,
    UnifiedCard,
)


class MockWecomClient:
    """Mock WecomClient for testing"""

    def __init__(self):
        self.sent_messages: list[dict] = []
        self.sent_cards: list[dict] = []
        self.updated_cards: list[dict] = []
        self._user_info = {
            "userid": "user_test",
            "name": "Test User",
            "email": "test@example.com",
            "mobile": "13800138000",
        }

    async def send_text_message(self, user_id: str, content: str) -> str:
        self.sent_messages.append({
            "user_id": user_id,
            "content": content,
        })
        return f"msgid_{len(self.sent_messages)}"

    async def send_template_card(self, user_id: str, card: dict) -> str:
        self.sent_cards.append({
            "user_id": user_id,
            "card": card,
        })
        return f"msgid_{len(self.sent_cards)}"

    async def update_template_card(self, response_code: str, card: dict) -> bool:
        self.updated_cards.append({
            "response_code": response_code,
            "card": card,
        })
        return True

    async def get_user_info(self, user_id: str) -> dict:
        return self._user_info


class TestWecomPlatformAdapterInit:
    """Test adapter initialization"""

    def test_platform_property(self):
        """Platform property returns WECOM"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        assert adapter.platform == Platform.WECOM


class TestWecomPlatformAdapterParseMessage:
    """Test message parsing"""

    @pytest.mark.asyncio
    async def test_parse_text_message_from_dict(self):
        """Parses text message from dict"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "text",
            "FromUserName": "user_123",
            "MsgId": "msg_456",
            "Content": "Hello, world!",
            "CreateTime": "1706346000",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        assert result.platform == Platform.WECOM
        assert result.message_id == "msg_456"
        assert result.chat_id == "user_123"
        assert result.sender_id == "user_123"
        assert result.message_type == MessageType.TEXT
        assert result.content == "Hello, world!"

    @pytest.mark.asyncio
    async def test_parse_text_message_from_xml(self):
        """Parses text message from XML Element"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        xml_str = """
        <xml>
            <MsgType>text</MsgType>
            <FromUserName>user_xml</FromUserName>
            <MsgId>msg_xml_123</MsgId>
            <Content>XML message</Content>
            <CreateTime>1706346000</CreateTime>
        </xml>
        """
        root = ET.fromstring(xml_str)

        result = await adapter.parse_message(root)

        assert result is not None
        assert result.sender_id == "user_xml"
        assert result.content == "XML message"

    @pytest.mark.asyncio
    async def test_parse_image_message(self):
        """Parses image message"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "image",
            "FromUserName": "user_123",
            "MsgId": "msg_img",
            "MediaId": "media_123",
            "PicUrl": "https://example.com/img.jpg",
            "CreateTime": "1706346000",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        assert result.message_type == MessageType.IMAGE
        assert "[图片]" in result.content
        assert len(result.attachments) == 1
        assert result.attachments[0]["type"] == "image"
        assert result.attachments[0]["url"] == "https://example.com/img.jpg"

    @pytest.mark.asyncio
    async def test_parse_voice_message(self):
        """Parses voice message"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "voice",
            "FromUserName": "user_123",
            "MsgId": "msg_voice",
            "MediaId": "media_voice",
            "CreateTime": "1706346000",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        assert "[语音]" in result.content
        assert len(result.attachments) == 1

    @pytest.mark.asyncio
    async def test_parse_file_message(self):
        """Parses file message"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "file",
            "FromUserName": "user_123",
            "MsgId": "msg_file",
            "MediaId": "media_file",
            "CreateTime": "1706346000",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        assert result.message_type == MessageType.FILE
        assert "[文件]" in result.content

    @pytest.mark.asyncio
    async def test_skip_empty_user(self):
        """Returns None for empty user"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "text",
            "FromUserName": "",
            "Content": "No user",
        }

        result = await adapter.parse_message(raw_event)

        assert result is None


class TestWecomPlatformAdapterParseAction:
    """Test action parsing"""

    @pytest.mark.asyncio
    async def test_parse_card_action_simple(self):
        """Parses simple action key"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_callback = {
            "FromUserName": "user_123",
            "EventKey": "confirm_requirement",
            "ResponseCode": "response_code_123",
            "TaskId": "task_456",
        }

        result = await adapter.parse_action(raw_callback)

        assert result is not None
        assert result.platform == Platform.WECOM
        assert result.action_id == "confirm_requirement"
        assert result.message_id == "response_code_123"
        assert result.operator_id == "user_123"

    @pytest.mark.asyncio
    async def test_parse_card_action_with_payload(self):
        """Parses action key with JSON payload"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_callback = {
            "FromUserName": "user_123",
            "EventKey": 'confirm:{"req_id": "req_789"}',
            "ResponseCode": "response_code_123",
        }

        result = await adapter.parse_action(raw_callback)

        assert result is not None
        assert result.action_id == "confirm"
        assert result.value == {"req_id": "req_789"}

    @pytest.mark.asyncio
    async def test_skip_empty_event_key(self):
        """Returns None for empty EventKey"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_callback = {
            "FromUserName": "user_123",
            "EventKey": "",
        }

        result = await adapter.parse_action(raw_callback)

        assert result is None


class TestWecomPlatformAdapterSendCard:
    """Test card sending"""

    @pytest.mark.asyncio
    async def test_send_card(self):
        """Sends card to user"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        card = UnifiedCard(
            title="Test Card",
            content="Card content with **markdown**",
            status="pending",
        )

        message_id = await adapter.send_card("user_123", card)

        assert message_id == "msgid_1"
        assert len(client.sent_cards) == 1
        assert client.sent_cards[0]["user_id"] == "user_123"

        sent_card = client.sent_cards[0]["card"]
        assert sent_card["main_title"]["title"] == "[pending] Test Card"

    @pytest.mark.asyncio
    async def test_send_card_with_actions(self):
        """Sends card with buttons"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        card = UnifiedCard(
            title="Action Card",
            content="Click a button",
            actions=[
                CardAction(
                    label="Confirm",
                    action_id="confirm",
                    style=CardActionStyle.PRIMARY,
                ),
                CardAction(
                    label="Reject",
                    action_id="reject",
                    style=CardActionStyle.DANGER,
                ),
            ],
        )

        await adapter.send_card("user_123", card)

        sent_card = client.sent_cards[0]["card"]
        assert "button_list" in sent_card
        assert len(sent_card["button_list"]) == 2
        assert sent_card["button_list"][0]["text"] == "Confirm"
        assert sent_card["button_list"][0]["style"] == 1  # PRIMARY = 1
        assert sent_card["button_list"][1]["style"] == 3  # DANGER = 3

    @pytest.mark.asyncio
    async def test_send_card_with_fields(self):
        """Sends card with horizontal content"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        card = UnifiedCard(
            title="Field Card",
            content="Content",
            fields=[
                {"label": "Category", "value": "Feature"},
                {"label": "Priority", "value": "High"},
            ],
        )

        await adapter.send_card("user_123", card)

        sent_card = client.sent_cards[0]["card"]
        assert "horizontal_content_list" in sent_card
        assert len(sent_card["horizontal_content_list"]) == 2


class TestWecomPlatformAdapterSendText:
    """Test text sending"""

    @pytest.mark.asyncio
    async def test_send_text(self):
        """Sends text message"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        message_id = await adapter.send_text("user_123", "Hello!")

        assert message_id == "msgid_1"
        assert len(client.sent_messages) == 1
        assert client.sent_messages[0]["user_id"] == "user_123"
        assert client.sent_messages[0]["content"] == "Hello!"


class TestWecomPlatformAdapterUpdateCard:
    """Test card updating"""

    @pytest.mark.asyncio
    async def test_update_card(self):
        """Updates card successfully"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        card = UnifiedCard(title="Updated", content="New content")

        result = await adapter.update_card("response_code_123", card)

        assert result is True
        assert len(client.updated_cards) == 1
        assert client.updated_cards[0]["response_code"] == "response_code_123"


class TestWecomPlatformAdapterUserInfo:
    """Test user info retrieval"""

    @pytest.mark.asyncio
    async def test_get_user_email(self):
        """Gets user email"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        email = await adapter.get_user_email("user_123")

        assert email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_email_not_found(self):
        """Returns None when email not available"""
        client = MockWecomClient()
        client._user_info = {"userid": "user_123", "name": "No Email"}
        adapter = WecomPlatformAdapter(client)

        email = await adapter.get_user_email("user_123")

        assert email is None

    @pytest.mark.asyncio
    async def test_get_user_name(self):
        """Gets user name"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        name = await adapter.get_user_name("user_123")

        assert name == "Test User"

    @pytest.mark.asyncio
    async def test_user_info_caching(self):
        """Caches user info"""
        client = MockWecomClient()
        client.get_user_info = AsyncMock(return_value={
            "name": "Cached User",
            "email": "cached@example.com",
        })

        adapter = WecomPlatformAdapter(client)

        # First call
        await adapter.get_user_email("user_test")
        # Second call (should use cache)
        await adapter.get_user_name("user_test")

        # Should only call API once
        assert client.get_user_info.call_count == 1


class TestWecomPlatformAdapterEventKeyParsing:
    """Test EventKey parsing edge cases"""

    @pytest.mark.asyncio
    async def test_parse_action_invalid_json(self):
        """Handles invalid JSON in EventKey gracefully"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_callback = {
            "FromUserName": "user_123",
            "EventKey": "confirm:not_valid_json",
            "ResponseCode": "response_123",
        }

        result = await adapter.parse_action(raw_callback)

        assert result is not None
        assert result.action_id == "confirm"
        assert result.value == {}  # Invalid JSON becomes empty dict

    @pytest.mark.asyncio
    async def test_parse_action_non_dict_json(self):
        """Handles non-dict JSON in EventKey"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_callback = {
            "FromUserName": "user_123",
            "EventKey": 'confirm:"just_a_string"',
            "ResponseCode": "response_123",
        }

        result = await adapter.parse_action(raw_callback)

        assert result is not None
        assert result.action_id == "confirm"
        assert result.value == {"value": "just_a_string"}


class TestWecomPlatformAdapterTimestamp:
    """Test timestamp parsing"""

    @pytest.mark.asyncio
    async def test_parse_valid_timestamp(self):
        """Parses valid Unix timestamp"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "text",
            "FromUserName": "user_123",
            "Content": "Test",
            "CreateTime": "1706346000",  # 2024-01-27 10:00:00 UTC
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        assert result.timestamp.year == 2024
        assert result.timestamp.month == 1
        assert result.timestamp.day == 27

    @pytest.mark.asyncio
    async def test_parse_empty_timestamp(self):
        """Uses current time for empty timestamp"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "text",
            "FromUserName": "user_123",
            "Content": "Test",
            "CreateTime": "",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        # Should be recent (within last minute)
        now = datetime.now(UTC)
        diff = abs((now - result.timestamp).total_seconds())
        assert diff < 60

    @pytest.mark.asyncio
    async def test_parse_invalid_timestamp(self):
        """Uses current time for invalid timestamp"""
        client = MockWecomClient()
        adapter = WecomPlatformAdapter(client)

        raw_event = {
            "MsgType": "text",
            "FromUserName": "user_123",
            "Content": "Test",
            "CreateTime": "not_a_number",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        # Should use current time
        now = datetime.now(UTC)
        diff = abs((now - result.timestamp).total_seconds())
        assert diff < 60
