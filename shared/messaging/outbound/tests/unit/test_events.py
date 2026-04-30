"""Tests for channel gateway events."""
from shared.messaging.outbound.core.enums import ChatType
from shared.messaging.outbound.models.events import (
    AdapterStatusPayload,
    ChannelEventTypes,
    MessageDeliveredPayload,
    MessageInboundPayload,
    MessageOutboundPayload,
)
from shared.messaging.outbound.models.messages import (
    ChatContext,
    DeliveryResult,
    InboundMessage,
    MessageAuthor,
    OutboundMessage,
)


class TestChannelEventTypes:
    def test_message_inbound(self):
        assert ChannelEventTypes.MESSAGE_INBOUND == "channel.message.inbound"

    def test_message_outbound(self):
        assert ChannelEventTypes.MESSAGE_OUTBOUND == "channel.message.outbound"

    def test_message_delivered(self):
        assert ChannelEventTypes.MESSAGE_DELIVERED == "channel.message.delivered"

    def test_message_edited(self):
        assert ChannelEventTypes.MESSAGE_EDITED == "channel.message.edited"

    def test_message_deleted(self):
        assert ChannelEventTypes.MESSAGE_DELETED == "channel.message.deleted"

    def test_reaction_added(self):
        assert ChannelEventTypes.REACTION_ADDED == "channel.reaction.added"

    def test_read_receipt(self):
        assert ChannelEventTypes.READ_RECEIPT == "channel.read.receipt"

    def test_adapter_status(self):
        assert ChannelEventTypes.ADAPTER_STATUS == "channel.adapter.status"


class TestMessageInboundPayload:
    def test_create_from_inbound_message(self):
        msg = InboundMessage(
            channel_id="telegram",
            platform_message_id="123",
            author=MessageAuthor(platform_user_id="user1"),
            chat=ChatContext(platform_chat_id="chat1", chat_type=ChatType.DM),
            content="Hello",
        )
        payload = MessageInboundPayload(message=msg)
        assert payload.message.channel_id == "telegram"


class TestMessageOutboundPayload:
    def test_create_from_outbound_message(self):
        msg = OutboundMessage(
            channel_id="slack",
            target_chat_id="channel1",
            content="Hello",
        )
        payload = MessageOutboundPayload(message=msg)
        assert payload.message.target_chat_id == "channel1"


class TestMessageDeliveredPayload:
    def test_create_success(self):
        result = DeliveryResult(success=True, platform_message_id="sent1")
        payload = MessageDeliveredPayload(
            message_id="msg_123",
            channel_id="discord",
            result=result,
        )
        assert payload.result.success is True

    def test_create_failure(self):
        result = DeliveryResult(success=False, error_code="FAILED")
        payload = MessageDeliveredPayload(
            message_id="msg_456",
            channel_id="teams",
            result=result,
        )
        assert payload.result.success is False


class TestAdapterStatusPayload:
    def test_connected_status(self):
        payload = AdapterStatusPayload(
            channel_id="telegram",
            status="connected",
        )
        assert payload.status == "connected"
        assert payload.error_message is None

    def test_error_status(self):
        payload = AdapterStatusPayload(
            channel_id="whatsapp",
            status="error",
            error_message="Connection refused",
        )
        assert payload.status == "error"
        assert payload.error_message == "Connection refused"
