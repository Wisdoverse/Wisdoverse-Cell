# shared/integrations/wecom/tests/test_cards.py
"""Tests for WeCom card builder."""

from shared.integrations.channels import CardAction, CardElement, ChannelCard
from shared.integrations.wecom.cards.builder import WecomCardBuilder


class TestWecomCardBuilder:
    def test_build_button_interaction_card(self):
        builder = WecomCardBuilder()
        card = builder.set_title("Test Card").set_description("Description").build()

        assert card["card_type"] == "button_interaction"
        assert card["main_title"]["title"] == "Test Card"
        assert card["sub_title_text"] == "Description"

    def test_add_buttons(self):
        builder = WecomCardBuilder()
        card = (
            builder
            .set_title("Test")
            .add_button("Confirm", "confirm", style=1)
            .add_button("Reject", "reject", style=2)
            .build()
        )

        assert len(card["button_list"]) == 2
        assert card["button_list"][0]["text"] == "Confirm"
        assert card["button_list"][0]["style"] == 1

    def test_max_two_buttons(self):
        builder = WecomCardBuilder()
        card = (
            builder
            .set_title("Test")
            .add_button("Btn1", "b1")
            .add_button("Btn2", "b2")
            .add_button("Btn3", "b3")  # Should be ignored
            .build()
        )

        assert len(card["button_list"]) == 2

    def test_add_horizontal_content(self):
        builder = WecomCardBuilder()
        card = (
            builder
            .set_title("Test")
            .add_horizontal_content("Priority", "HIGH")
            .add_horizontal_content("Category", "Feature")
            .build()
        )

        assert len(card["horizontal_content_list"]) == 2
        assert card["horizontal_content_list"][0]["keyname"] == "Priority"
        assert card["horizontal_content_list"][0]["value"] == "HIGH"


class TestConvertFromChannelCard:
    def test_convert_simple_card(self):
        channel_card = ChannelCard(
            card_id="req_1",
            title="New Requirement",
            elements=[
                CardElement(element_type="text", content="This is a requirement")
            ],
            actions=[
                CardAction(action_id="confirm", label="Confirm", style="primary"),
                CardAction(action_id="reject", label="Reject", style="danger"),
            ]
        )

        wecom_card = WecomCardBuilder.from_channel_card(channel_card)

        assert wecom_card["main_title"]["title"] == "New Requirement"
        assert wecom_card["sub_title_text"] == "This is a requirement"
        assert len(wecom_card["button_list"]) == 2

    def test_convert_card_with_fields(self):
        channel_card = ChannelCard(
            card_id="req_1",
            title="Requirement",
            elements=[
                CardElement(element_type="text", content="Description"),
                CardElement(
                    element_type="field",
                    fields=[
                        {"label": "Priority", "value": "HIGH"},
                        {"label": "Category", "value": "Feature"},
                    ]
                ),
            ],
            actions=[]
        )

        wecom_card = WecomCardBuilder.from_channel_card(channel_card)

        assert len(wecom_card["horizontal_content_list"]) == 2
