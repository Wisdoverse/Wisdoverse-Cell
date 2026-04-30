# shared/integrations/feishu/tests/test_adapter.py
"""Tests for Feishu MessageChannel adapter."""
import pytest

from shared.integrations.channels import (
    CardAction,
    CardElement,
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    MessageChannel,
)
from shared.integrations.feishu.adapter import FeishuChannelAdapter

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_card(
    *,
    card_id: str = "card_001",
    title: str = "Test Card",
    elements: list[CardElement] | None = None,
    actions: list[CardAction] | None = None,
) -> ChannelCard:
    return ChannelCard(
        card_id=card_id,
        title=title,
        elements=elements or [],
        actions=actions or [],
    )


# ──────────────────────────────────────────────
# TestFeishuChannelAdapter
# ──────────────────────────────────────────────


class TestFeishuChannelAdapter:
    """Public interface tests for FeishuChannelAdapter."""

    @pytest.fixture
    def adapter(self, mock_feishu_client):
        return FeishuChannelAdapter(client=mock_feishu_client)

    # ── channel_name ──

    def test_channel_name__returns_feishu(self, adapter):
        assert adapter.channel_name == "feishu"

    def test_channel_name__implements_message_channel(self, adapter):
        assert isinstance(adapter, MessageChannel)

    # ── send_message ──

    @pytest.mark.asyncio
    async def test_send_message__markdown__uses_add_markdown(
        self, adapter, mock_feishu_client
    ):
        msg = ChannelMessage(content="# Hello", message_type="markdown")

        result = await adapter.send_message("ou_user_001", msg)

        assert result == "msg_card_001"
        mock_feishu_client.send_card.assert_awaited_once()
        call_kwargs = mock_feishu_client.send_card.call_args.kwargs
        assert call_kwargs["receive_id"] == "ou_user_001"
        assert call_kwargs["receive_id_type"] == "open_id"
        card = call_kwargs["card"]
        # CardBuilder.add_markdown produces tag="lark_md"
        assert card["elements"][0] == {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "# Hello"},
        }

    @pytest.mark.asyncio
    async def test_send_message__plain_text__uses_add_plain_text(
        self, adapter, mock_feishu_client
    ):
        msg = ChannelMessage(content="plain hello", message_type="text")

        result = await adapter.send_message("ou_user_002", msg)

        assert result == "msg_card_001"
        mock_feishu_client.send_card.assert_awaited_once()
        card = mock_feishu_client.send_card.call_args.kwargs["card"]
        assert card["elements"][0] == {
            "tag": "div",
            "text": {"tag": "plain_text", "content": "plain hello"},
        }

    @pytest.mark.asyncio
    async def test_send_message__no_header_in_simple_message(
        self, adapter, mock_feishu_client
    ):
        """send_message builds a card without a header."""
        msg = ChannelMessage(content="hi")
        await adapter.send_message("ou_user_001", msg)

        card = mock_feishu_client.send_card.call_args.kwargs["card"]
        assert "header" not in card

    # ── send_card ──

    @pytest.mark.asyncio
    async def test_send_card__builds_card_with_header(
        self, adapter, mock_feishu_client
    ):
        card = _make_card(title="Requirement #42")

        result = await adapter.send_card("ou_user_001", card)

        assert result == "msg_card_001"
        mock_feishu_client.send_card.assert_awaited_once()
        call_kwargs = mock_feishu_client.send_card.call_args.kwargs
        assert call_kwargs["receive_id"] == "ou_user_001"
        assert call_kwargs["receive_id_type"] == "open_id"
        feishu_card = call_kwargs["card"]
        assert feishu_card["header"] == {
            "title": {"tag": "plain_text", "content": "Requirement #42"},
            "template": "blue",
        }

    # ── update_card ──

    @pytest.mark.asyncio
    async def test_update_card__calls_client_update(
        self, adapter, mock_feishu_client
    ):
        card = _make_card(title="Updated Card")

        result = await adapter.update_card("msg_existing_001", card)

        assert result is True
        mock_feishu_client.update_card.assert_awaited_once()
        args = mock_feishu_client.update_card.call_args
        assert args[0][0] == "msg_existing_001"
        feishu_card = args[0][1]
        assert feishu_card["header"]["title"]["content"] == "Updated Card"

    # ── handle_callback ──

    @pytest.mark.asyncio
    async def test_handle_callback__returns_success(self, adapter):
        payload = {
            "action": {"value": {"action": "approve", "req_id": "req_001"}},
            "operator": {"open_id": "ou_operator_001"},
        }

        result = await adapter.handle_callback(payload)

        assert isinstance(result, ChannelResponse)
        assert result.success is True


# ──────────────────────────────────────────────
# TestConvertToFeishuCard
# ──────────────────────────────────────────────


class TestConvertToFeishuCard:
    """Tests for _convert_to_feishu_card internal method."""

    @pytest.fixture
    def adapter(self, mock_feishu_client):
        return FeishuChannelAdapter(client=mock_feishu_client)

    # ── element_type parametrize ──

    @pytest.mark.parametrize(
        "element, expected_element",
        [
            pytest.param(
                CardElement(element_type="text", content="Hello world"),
                {
                    "tag": "div",
                    "text": {"tag": "plain_text", "content": "Hello world"},
                },
                id="text",
            ),
            pytest.param(
                CardElement(
                    element_type="field",
                    fields=[
                        {"label": "Priority", "value": "HIGH"},
                        {"label": "Status", "value": "Pending"},
                    ],
                ),
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": "**Priority**\nHIGH",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": "**Status**\nPending",
                            },
                        },
                    ],
                },
                id="field",
            ),
            pytest.param(
                CardElement(element_type="divider"),
                {"tag": "hr"},
                id="divider",
            ),
        ],
    )
    def test_element_types__parametrized(self, adapter, element, expected_element):
        card = _make_card(elements=[element])

        result = adapter._convert_to_feishu_card(card)

        assert result["elements"][0] == expected_element

    def test_text_element__none_content__uses_empty_string(self, adapter):
        card = _make_card(
            elements=[CardElement(element_type="text", content=None)]
        )

        result = adapter._convert_to_feishu_card(card)

        assert result["elements"][0]["text"]["content"] == ""

    def test_field_element__without_fields__skipped(self, adapter):
        """A field element with fields=None is ignored."""
        card = _make_card(
            elements=[CardElement(element_type="field", fields=None)]
        )

        result = adapter._convert_to_feishu_card(card)

        # Only the header is set; no elements added for the field
        assert result["elements"] == []

    # ── action buttons ──

    def test_action_buttons__primary_style(self, adapter):
        card = _make_card(
            actions=[
                CardAction(
                    action_id="approve",
                    label="Approve",
                    style="primary",
                    payload={"req_id": "req_001"},
                )
            ]
        )

        result = adapter._convert_to_feishu_card(card)

        action_block = result["elements"][-1]
        assert action_block["tag"] == "action"
        button = action_block["actions"][0]
        assert button == {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "Approve"},
            "type": "primary",
            "value": {"action": "approve", "req_id": "req_001"},
        }

    def test_action_buttons__danger_style(self, adapter):
        card = _make_card(
            actions=[
                CardAction(
                    action_id="reject",
                    label="Reject",
                    style="danger",
                    payload={},
                )
            ]
        )

        result = adapter._convert_to_feishu_card(card)

        button = result["elements"][-1]["actions"][0]
        assert button["type"] == "danger"
        assert button["text"]["content"] == "Reject"
        assert button["value"] == {"action": "reject"}

    def test_action_buttons__default_style(self, adapter):
        card = _make_card(
            actions=[
                CardAction(
                    action_id="details",
                    label="View Details",
                    style="default",
                    payload={"page": "1"},
                )
            ]
        )

        result = adapter._convert_to_feishu_card(card)

        button = result["elements"][-1]["actions"][0]
        assert button["type"] == "default"
        assert button["text"]["content"] == "View Details"
        assert button["value"] == {"action": "details", "page": "1"}

    def test_empty_elements_and_actions(self, adapter):
        card = _make_card(elements=[], actions=[])

        result = adapter._convert_to_feishu_card(card)

        assert result["elements"] == []
        assert result["header"]["title"]["content"] == "Test Card"
        assert result["config"] == {"wide_screen_mode": True}

    def test_multiple_actions(self, adapter):
        card = _make_card(
            actions=[
                CardAction(action_id="approve", label="Approve", style="primary"),
                CardAction(action_id="reject", label="Reject", style="danger"),
                CardAction(
                    action_id="defer",
                    label="Defer",
                    style="default",
                    payload={"reason": "later"},
                ),
            ]
        )

        result = adapter._convert_to_feishu_card(card)

        action_block = result["elements"][-1]
        assert action_block["tag"] == "action"
        buttons = action_block["actions"]
        assert len(buttons) == 3
        assert buttons[0]["type"] == "primary"
        assert buttons[0]["value"] == {"action": "approve"}
        assert buttons[1]["type"] == "danger"
        assert buttons[1]["value"] == {"action": "reject"}
        assert buttons[2]["type"] == "default"
        assert buttons[2]["value"] == {"action": "defer", "reason": "later"}
