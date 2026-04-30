"""Tests for channel message models."""
from datetime import UTC, datetime

from shared.messaging.outbound.core.enums import ChatType, MediaType, ParseMode
from shared.messaging.outbound.models.messages import (
    ChatContext,
    DeliveryResult,
    InboundMessage,
    MediaAttachment,
    MessageAuthor,
    OutboundMessage,
)


class TestMediaAttachment:
    def test_create_with_defaults(self):
        attachment = MediaAttachment(media_type=MediaType.IMAGE)
        assert attachment.media_id.startswith("med_")
        assert attachment.media_type == MediaType.IMAGE
        assert attachment.url is None

    def test_create_with_all_fields(self):
        attachment = MediaAttachment(
            media_type=MediaType.VIDEO,
            url="https://example.com/video.mp4",
            mime_type="video/mp4",
            file_name="video.mp4",
            file_size=1024000,
            duration=120,
        )
        assert attachment.url == "https://example.com/video.mp4"
        assert attachment.duration == 120


class TestMessageAuthor:
    def test_create_minimal(self):
        author = MessageAuthor(platform_user_id="user123")
        assert author.platform_user_id == "user123"
        assert author.is_bot is False

    def test_create_full(self):
        author = MessageAuthor(
            platform_user_id="user123",
            display_name="John Doe",
            username="johndoe",
            avatar_url="https://example.com/avatar.png",
            is_bot=True,
        )
        assert author.display_name == "John Doe"
        assert author.is_bot is True


class TestChatContext:
    def test_create_dm(self):
        chat = ChatContext(platform_chat_id="chat123", chat_type=ChatType.DM)
        assert chat.chat_type == ChatType.DM

    def test_create_group(self):
        chat = ChatContext(
            platform_chat_id="group456",
            chat_type=ChatType.GROUP,
            chat_name="Test Group",
        )
        assert chat.chat_name == "Test Group"


class TestInboundMessage:
    def test_create_minimal(self):
        msg = InboundMessage(
            channel_id="telegram",
            platform_message_id="msg123",
            author=MessageAuthor(platform_user_id="user1"),
            chat=ChatContext(platform_chat_id="chat1", chat_type=ChatType.DM),
            content="Hello",
        )
        assert msg.message_id.startswith("msg_")
        assert msg.channel_id == "telegram"
        assert msg.content == "Hello"
        assert isinstance(msg.timestamp, datetime)

    def test_create_with_attachments(self):
        msg = InboundMessage(
            channel_id="slack",
            platform_message_id="msg456",
            author=MessageAuthor(platform_user_id="user2"),
            chat=ChatContext(platform_chat_id="chat2", chat_type=ChatType.GROUP),
            attachments=[MediaAttachment(media_type=MediaType.IMAGE)],
        )
        assert len(msg.attachments) == 1


class TestOutboundMessage:
    def test_create_text_message(self):
        msg = OutboundMessage(
            channel_id="discord",
            target_chat_id="channel123",
            content="Hello World",
        )
        assert msg.message_id.startswith("msg_")
        assert msg.parse_mode == ParseMode.PLAIN
        assert msg.silent is False

    def test_create_with_markdown(self):
        msg = OutboundMessage(
            channel_id="telegram",
            target_chat_id="chat789",
            content="**Bold** text",
            parse_mode=ParseMode.MARKDOWN,
        )
        assert msg.parse_mode == ParseMode.MARKDOWN


class TestDeliveryResult:
    def test_success_result(self):
        result = DeliveryResult(
            success=True,
            platform_message_id="sent123",
            delivered_at=datetime.now(UTC),
        )
        assert result.success is True
        assert result.error_code is None

    def test_failure_result(self):
        result = DeliveryResult(
            success=False,
            error_code="RATE_LIMITED",
            error_message="Too many requests",
        )
        assert result.success is False
        assert result.error_code == "RATE_LIMITED"
