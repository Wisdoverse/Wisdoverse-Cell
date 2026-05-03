# shared/integrations/wecom/cards/builder.py
"""
WecomCardBuilder - WeCom template card builder.

WeCom uses template cards rather than Feishu-style interactive cards.
Key constraints:
- At most two buttons.
- Fixed template structure.
"""
import json
from typing import Literal

from shared.core.channels import ChannelCard


class WecomCardBuilder:
    """
    WeCom template card builder.

    Usage:
        card = (
            WecomCardBuilder()
            .set_title("Title")
            .set_description("Description")
            .add_button("Confirm", "confirm", style=1)
            .add_button("Reject", "reject", style=2)
            .build()
        )
    """

    MAX_BUTTONS = 2

    def __init__(self):
        self._card_type = "button_interaction"
        self._title = ""
        self._description = ""
        self._source_desc = "Requirement Manager"
        self._horizontal_content: list[dict] = []
        self._buttons: list[dict] = []

    def set_title(self, title: str) -> "WecomCardBuilder":
        """Set the main title."""
        self._title = title
        return self

    def set_description(self, description: str) -> "WecomCardBuilder":
        """Set the subtitle or description."""
        self._description = description
        return self

    def set_source(self, desc: str) -> "WecomCardBuilder":
        """Set the source description."""
        self._source_desc = desc
        return self

    def add_horizontal_content(
        self,
        key: str,
        value: str,
        content_type: int = 0,
    ) -> "WecomCardBuilder":
        """Add a horizontal content item."""
        self._horizontal_content.append({
            "keyname": key,
            "value": value,
            "type": content_type,
        })
        return self

    def add_button(
        self,
        text: str,
        key: str,
        style: Literal[1, 2, 3] = 1,
    ) -> "WecomCardBuilder":
        """Add a button, capped by the WeCom template limit."""
        if len(self._buttons) >= self.MAX_BUTTONS:
            return self

        self._buttons.append({
            "text": text,
            "style": style,
            "key": key,
        })
        return self

    def build(self) -> dict:
        """Build a WeCom template card."""
        card = {
            "card_type": self._card_type,
            "source": {
                "desc": self._source_desc,
            },
            "main_title": {
                "title": self._title,
            },
            "sub_title_text": self._description,
        }

        if self._horizontal_content:
            card["horizontal_content_list"] = self._horizontal_content

        if self._buttons:
            card["button_list"] = self._buttons

        return card

    @classmethod
    def from_channel_card(cls, card: ChannelCard) -> dict:
        """Convert a generic ChannelCard to a WeCom template card."""
        builder = cls()
        builder.set_title(card.title)

        # Use the first text element as the description.
        for element in card.elements:
            if element.element_type == "text" and element.content:
                builder.set_description(element.content)
                break

        # Convert field elements.
        for element in card.elements:
            if element.element_type == "field" and element.fields:
                for field in element.fields:
                    builder.add_horizontal_content(
                        key=field.get("label", ""),
                        value=field.get("value", "")
                    )

        # Convert buttons.
        for action in card.actions[:cls.MAX_BUTTONS]:
            style = 1
            if action.style == "danger":
                style = 2
            elif action.style == "default":
                style = 2

            key = f"{card.card_id}:{action.action_id}"
            if action.payload:
                key = f"{card.card_id}:{action.action_id}:{json.dumps(action.payload)}"

            builder.add_button(
                text=action.label,
                key=key,
                style=style
            )

        return builder.build()
