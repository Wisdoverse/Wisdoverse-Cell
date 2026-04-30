# shared/integrations/feishu/tests/test_platform_adapter.py
"""Tests for FeishuPlatformAdapter."""
import json
from datetime import UTC, datetime

import pytest

from shared.integrations.feishu.platform_adapter import FeishuPlatformAdapter
from shared.messaging.inbound.models import (
    CardAction,
    CardActionStyle,
    MessageType,
    Platform,
    UnifiedCard,
)

from .conftest import make_card_action, make_feishu_event

# ── Helpers ──────────────────────────────────────────────


def _make_unified_card(**overrides) -> UnifiedCard:
    """Build a UnifiedCard with sensible defaults, overridable per-field."""
    defaults = dict(
        title="Test Card",
        content="Some markdown content",
        status=None,
        status_color=None,
        priority=None,
        fields=[],
        actions=[],
        context={},
    )
    defaults.update(overrides)
    return UnifiedCard(**defaults)


# ── TestParseMessage ─────────────────────────────────────


class TestParseMessage:
    """parse_message: raw feishu event -> UnifiedMessage | None."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "msg_type, content_json, expected_type, expected_content_substr",
        [
            pytest.param(
                "text",
                '{"text": "hello world"}',
                MessageType.TEXT,
                "hello world",
                id="text_message",
            ),
            pytest.param(
                "post",
                json.dumps({
                    "title": "Post Title",
                    "content": [[{"tag": "text", "text": "paragraph one"}]],
                }),
                MessageType.POST,
                "Post Title",
                id="post_message",
            ),
            pytest.param(
                "image",
                '{"image_key": "img_v2_abc123"}',
                MessageType.IMAGE,
                "[图片: img_v2_abc123]",
                id="image_message",
            ),
            pytest.param(
                "file",
                '{"file_key": "file_abc", "file_name": "report.pdf"}',
                MessageType.FILE,
                "[文件: report.pdf]",
                id="file_message",
            ),
        ],
    )
    async def test_parse_message__msg_types__returns_unified_message(
        self,
        mock_feishu_client,
        msg_type,
        content_json,
        expected_type,
        expected_content_substr,
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(
            msg_type=msg_type,
            content=content_json,
            message_id="msg_001",
            chat_id="oc_chat_001",
            sender_open_id="ou_user_001",
            chat_type="group",
        )

        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.platform == Platform.FEISHU
        assert result.message_id == "msg_001"
        assert result.chat_id == "oc_chat_001"
        assert result.sender_id == "ou_user_001"
        assert result.message_type == expected_type
        assert expected_content_substr in result.content

    @pytest.mark.asyncio
    async def test_parse_message__bot_sender__returns_none(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(sender_type="app")

        result = await adapter.parse_message(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_message__empty_message_id__returns_none(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(message_id="")

        result = await adapter.parse_message(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_message__group_chat_type__maps_to_group(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(chat_type="group")

        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.chat_type == "group"

    @pytest.mark.asyncio
    async def test_parse_message__p2p_chat_type__maps_to_private(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(chat_type="p2p")

        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.chat_type == "private"

    @pytest.mark.asyncio
    async def test_parse_message__image__has_attachment(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(
            msg_type="image",
            content='{"image_key": "img_key_xyz"}',
        )

        result = await adapter.parse_message(raw)

        assert result is not None
        assert len(result.attachments) == 1
        assert result.attachments[0]["type"] == "image"
        assert result.attachments[0]["key"] == "img_key_xyz"
        assert result.attachments[0]["url"] == ""

    @pytest.mark.asyncio
    async def test_parse_message__file__has_attachment(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(
            msg_type="file",
            content='{"file_key": "fk_001", "file_name": "notes.txt"}',
        )

        result = await adapter.parse_message(raw)

        assert result is not None
        assert len(result.attachments) == 1
        assert result.attachments[0]["type"] == "file"
        assert result.attachments[0]["key"] == "fk_001"
        assert result.attachments[0]["name"] == "notes.txt"

    @pytest.mark.asyncio
    async def test_parse_message__valid_timestamp__parsed_correctly(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event(create_time="1706169600000")

        result = await adapter.parse_message(raw)

        assert result is not None
        expected = datetime.fromtimestamp(1706169600, tz=UTC)
        assert result.timestamp == expected

    @pytest.mark.asyncio
    async def test_parse_message__raw_data_preserved(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_feishu_event()

        result = await adapter.parse_message(raw)

        assert result is not None
        assert result.raw_data == raw


# ── TestParseAction ──────────────────────────────────────


class TestParseAction:
    """parse_action: raw card callback -> UnifiedAction | None."""

    @pytest.mark.asyncio
    async def test_parse_action__valid_callback__returns_unified_action(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = make_card_action(
            action_type="confirm_requirement",
            req_id="req_999",
            operator_open_id="ou_op_001",
        )
        raw["open_message_id"] = "om_card_001"

        result = await adapter.parse_action(raw)

        assert result is not None
        assert result.platform == Platform.FEISHU
        assert result.action_id == "confirm_requirement"
        assert result.message_id == "om_card_001"
        assert result.operator_id == "ou_op_001"
        assert result.value["req_id"] == "req_999"

    @pytest.mark.asyncio
    async def test_parse_action__empty_action_id__returns_none(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = {
            "action": {"value": {"action": ""}},
            "operator": {"open_id": "ou_op"},
        }

        result = await adapter.parse_action(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_action__missing_action_key__returns_none(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        raw = {
            "action": {"value": {}},
            "operator": {"open_id": "ou_op"},
        }

        result = await adapter.parse_action(raw)

        assert result is None


# ── TestSendCard ─────────────────────────────────────────


class TestSendCard:
    """send_card: routes by chat_id prefix and builds feishu card."""

    @pytest.mark.asyncio
    async def test_send_card__oc_prefix__receive_id_type_chat_id(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        card = _make_unified_card()

        await adapter.send_card("oc_group_chat_001", card)

        mock_feishu_client.send_card.assert_awaited_once()
        call_kwargs = mock_feishu_client.send_card.call_args
        assert call_kwargs.kwargs["receive_id"] == "oc_group_chat_001"
        assert call_kwargs.kwargs["receive_id_type"] == "chat_id"

    @pytest.mark.asyncio
    async def test_send_card__open_id__receive_id_type_open_id(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        card = _make_unified_card()

        await adapter.send_card("ou_user_001", card)

        call_kwargs = mock_feishu_client.send_card.call_args
        assert call_kwargs.kwargs["receive_id"] == "ou_user_001"
        assert call_kwargs.kwargs["receive_id_type"] == "open_id"

    @pytest.mark.asyncio
    async def test_send_card__returns_message_id(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        card = _make_unified_card()

        result = await adapter.send_card("oc_chat", card)

        assert result == "msg_card_001"

    @pytest.mark.asyncio
    async def test_send_card__card_has_header_and_elements(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        card = _make_unified_card(
            title="My Title",
            content="**bold**",
            status_color="green",
        )

        await adapter.send_card("oc_chat", card)

        sent_card = mock_feishu_client.send_card.call_args.kwargs["card"]
        assert sent_card["header"]["title"]["content"] == "My Title"
        assert sent_card["header"]["template"] == "green"
        assert any(
            el.get("text", {}).get("content") == "**bold**"
            for el in sent_card["elements"]
            if el.get("tag") == "div"
        )


    @pytest.mark.asyncio
    async def test_send_card__card_with_context__context_merged_into_button_values(
        self, mock_feishu_client
    ):
        """card.context dict should be merged into each action button's value."""
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        card = _make_unified_card(
            title="Ctx Card",
            content="body",
            actions=[
                CardAction(
                    action_id="do_thing",
                    label="Click",
                    style=CardActionStyle.PRIMARY,
                    value={"req_id": "r1"},
                ),
            ],
            context={"session_id": "ses_99", "chat_id": "oc_abc"},
        )

        await adapter.send_card("oc_chat", card)

        sent_card = mock_feishu_client.send_card.call_args.kwargs["card"]
        action_els = [el for el in sent_card["elements"] if el.get("tag") == "action"]
        assert len(action_els) == 1
        button = action_els[0]["actions"][0]
        assert button["value"]["action"] == "do_thing"
        assert button["value"]["req_id"] == "r1"
        assert button["value"]["session_id"] == "ses_99"
        assert button["value"]["chat_id"] == "oc_abc"


# ── TestSendText ─────────────────────────────────────────


class TestSendText:
    """send_text: wraps text as markdown card and sends."""

    @pytest.mark.asyncio
    async def test_send_text__sends_as_markdown_card(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        result = await adapter.send_text("oc_chat_001", "Hello world")

        assert result == "msg_card_001"
        mock_feishu_client.send_card.assert_awaited_once()
        call_kwargs = mock_feishu_client.send_card.call_args.kwargs
        assert call_kwargs["receive_id"] == "oc_chat_001"
        assert call_kwargs["receive_id_type"] == "chat_id"
        sent_card = call_kwargs["card"]
        md_elements = [
            el for el in sent_card["elements"]
            if el.get("tag") == "div"
            and el.get("text", {}).get("tag") == "lark_md"
        ]
        assert len(md_elements) == 1
        assert md_elements[0]["text"]["content"] == "Hello world"


# ── TestUpdateCard ───────────────────────────────────────


class TestUpdateCard:
    """update_card: delegates to client.update_card."""

    @pytest.mark.asyncio
    async def test_update_card__calls_client_update(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        card = _make_unified_card(title="Updated", content="new body")

        result = await adapter.update_card("om_msg_777", card)

        assert result is True
        mock_feishu_client.update_card.assert_awaited_once()
        args = mock_feishu_client.update_card.call_args
        assert args[0][0] == "om_msg_777"


# ── TestUserInfo ─────────────────────────────────────────


class TestUserInfo:
    """get_user_email / get_user_name with caching."""

    @pytest.mark.asyncio
    async def test_get_user_email__returns_email(self, mock_feishu_client):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        email = await adapter.get_user_email("ou_user_001")

        assert email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_name__returns_name(self, mock_feishu_client):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        name = await adapter.get_user_name("ou_user_001")

        assert name == "TestUser"

    @pytest.mark.asyncio
    async def test_get_user_info__cache_hit__no_second_api_call(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        await adapter.get_user_email("ou_same_user")
        await adapter.get_user_name("ou_same_user")

        mock_feishu_client.get_user_info.assert_awaited_once_with("ou_same_user")

    @pytest.mark.asyncio
    async def test_get_user_info__different_users__separate_api_calls(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        await adapter.get_user_email("ou_user_a")
        await adapter.get_user_email("ou_user_b")

        assert mock_feishu_client.get_user_info.await_count == 2


# ── TestParseContent ─────────────────────────────────────


class TestParseContent:
    """_parse_content: internal content parser."""

    def test_parse_content__post_multi_paragraph__extracts_all_tags(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        post_content = json.dumps({
            "title": "Meeting Notes",
            "content": [
                [
                    {"tag": "text", "text": "Action item:"},
                    {"tag": "at", "user_name": "Alice"},
                ],
                [
                    {"tag": "text", "text": "See "},
                    {"tag": "a", "text": "this link", "href": "https://example.com"},
                ],
            ],
        })

        content, msg_type, mentions, attachments = adapter._parse_content(
            "post", post_content
        )

        assert msg_type == MessageType.POST
        assert "Meeting Notes" in content
        assert "Action item:" in content
        assert "@Alice" in content
        assert "this link" in content
        assert mentions == []
        assert attachments == []

    def test_parse_content__json_decode_error__returns_raw_string(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)
        broken_json = "this is not json {{"

        content, msg_type, mentions, attachments = adapter._parse_content(
            "text", broken_json
        )

        assert content == broken_json
        assert msg_type == MessageType.TEXT
        assert mentions == []
        assert attachments == []

    def test_parse_content__unknown_type__returns_bracketed_type(
        self, mock_feishu_client
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        content, msg_type, mentions, attachments = adapter._parse_content(
            "sticker", '{"sticker_id": "stk_001"}'
        )

        assert content == "[sticker]"
        assert msg_type == MessageType.TEXT


# ── TestHeaderTemplate ───────────────────────────────────


class TestHeaderTemplate:
    """_get_header_template: status_color -> feishu template string."""

    @pytest.mark.parametrize(
        "status_color, expected_template",
        [
            pytest.param("green", "green", id="green"),
            pytest.param("orange", "orange", id="orange"),
            pytest.param("red", "red", id="red"),
            pytest.param("blue", "blue", id="blue"),
            pytest.param("grey", "grey", id="grey"),
            pytest.param("purple", "blue", id="unknown_falls_back_to_blue"),
            pytest.param(None, "blue", id="none_falls_back_to_blue"),
        ],
    )
    def test_get_header_template__color_mapping(
        self, mock_feishu_client, status_color, expected_template
    ):
        adapter = FeishuPlatformAdapter(mock_feishu_client)

        result = adapter._get_header_template(status_color)

        assert result == expected_template
