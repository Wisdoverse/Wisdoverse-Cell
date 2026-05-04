"""Tests for the shared Feishu card builder."""

from shared.integrations.feishu.cards.builder import CardBuilder


class TestCardBuilder:
    def test_set_header__with_subtitle__includes_subtitle_field(self):
        card = (
            CardBuilder()
            .set_header("Title", template="blue", subtitle="Sub")
            .build()
        )

        assert card["header"]["title"] == {"tag": "plain_text", "content": "Title"}
        assert card["header"]["template"] == "blue"
        assert card["header"]["subtitle"] == {"tag": "plain_text", "content": "Sub"}

    def test_add_button__appends_to_existing_action_group(self):
        card = (
            CardBuilder()
            .add_button("A", {"k": "a"}, button_type="primary")
            .add_button("B", {"k": "b"}, button_type="danger")
            .build()
        )

        action_el = card["elements"][0]
        assert action_el["tag"] == "action"
        assert len(action_el["actions"]) == 2
        assert action_el["actions"][0]["text"]["content"] == "A"
        assert action_el["actions"][1]["value"] == {"k": "b"}

    def test_add_button__creates_new_action_group_when_none_exists(self):
        card = (
            CardBuilder()
            .add_text("some text")
            .add_button("Click", {"action": "go"})
            .build()
        )

        assert card["elements"][0]["tag"] == "div"
        assert card["elements"][1]["tag"] == "action"
        assert card["elements"][1]["actions"][0]["text"]["content"] == "Click"

    def test_build__without_header__no_header_key(self):
        card = CardBuilder().add_text("hello").build()

        assert "header" not in card
        assert card["config"] == {"wide_screen_mode": True}
        assert len(card["elements"]) == 1

    def test_add_fields__creates_short_field_layout(self):
        card = (
            CardBuilder()
            .add_fields([("Label", "Value"), ("Status", "OK")], is_short=True)
            .build()
        )

        field_div = card["elements"][0]
        assert field_div["tag"] == "div"
        assert len(field_div["fields"]) == 2
        assert field_div["fields"][0]["text"]["tag"] == "lark_md"
        assert "**Label**\nValue" in field_div["fields"][0]["text"]["content"]

    def test_build_message__wraps_with_msg_type(self):
        msg = (
            CardBuilder()
            .set_header("T")
            .add_text("body")
            .build_message()
        )

        assert msg["msg_type"] == "interactive"
        assert msg["card"]["header"]["title"]["content"] == "T"

    def test_add_divider__adds_hr_element(self):
        card = CardBuilder().add_divider().build()

        assert card["elements"][0] == {"tag": "hr"}

    def test_add_note__adds_note_element(self):
        card = CardBuilder().add_note("Note").build()

        note = card["elements"][0]
        assert note["tag"] == "note"
        assert note["elements"][0] == {"tag": "plain_text", "content": "Note"}
