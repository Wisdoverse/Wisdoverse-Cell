"""Tests for channel types."""
from datetime import UTC, datetime

from shared.integrations.channels.types import (
    CardAction,
    CardElement,
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    IncomingMessage,
)


class TestChannelMessage:
    def test_text_message(self):
        msg = ChannelMessage(content="Hello")
        assert msg.content == "Hello"
        assert msg.message_type == "text"

    def test_markdown_message(self):
        msg = ChannelMessage(content="**Bold**", message_type="markdown")
        assert msg.message_type == "markdown"


class TestCardElement:
    def test_text_element(self):
        elem = CardElement(element_type="text", content="Hello")
        assert elem.element_type == "text"
        assert elem.content == "Hello"

    def test_field_element(self):
        elem = CardElement(
            element_type="field",
            fields=[{"label": "Priority", "value": "HIGH"}]
        )
        assert elem.fields[0]["label"] == "Priority"


class TestCardAction:
    def test_default_action(self):
        action = CardAction(action_id="confirm", label="Confirm")
        assert action.style == "default"
        assert action.payload == {}

    def test_primary_action_with_payload(self):
        action = CardAction(
            action_id="confirm",
            label="Confirm",
            style="primary",
            payload={"req_id": "123"}
        )
        assert action.style == "primary"
        assert action.payload["req_id"] == "123"


class TestChannelCard:
    def test_simple_card(self):
        card = ChannelCard(
            card_id="card_1",
            title="Test Card",
            elements=[CardElement(element_type="text", content="Hello")],
            actions=[CardAction(action_id="ok", label="OK")]
        )
        assert card.card_id == "card_1"
        assert len(card.elements) == 1
        assert len(card.actions) == 1


class TestIncomingMessage:
    def test_feishu_message(self):
        msg = IncomingMessage(
            channel="feishu",
            user_id="ou_xxx",
            message_id="msg_xxx",
            content="Hello",
            message_type="text",
            timestamp=datetime.now(UTC),
            raw={"event": {}}
        )
        assert msg.channel == "feishu"

    def test_wecom_message(self):
        msg = IncomingMessage(
            channel="wecom",
            user_id="user_xxx",
            message_id="msg_xxx",
            content="Hello",
            message_type="text",
            timestamp=datetime.now(UTC),
            raw={"MsgType": "text"}
        )
        assert msg.channel == "wecom"


class TestChannelResponse:
    def test_success_response(self):
        resp = ChannelResponse(success=True, message="OK")
        assert resp.success is True

    def test_error_response_with_data(self):
        resp = ChannelResponse(
            success=False,
            message="Error",
            data={"code": 500}
        )
        assert resp.success is False
        assert resp.data["code"] == 500
