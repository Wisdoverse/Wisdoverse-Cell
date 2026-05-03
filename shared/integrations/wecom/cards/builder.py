# shared/integrations/wecom/cards/builder.py
"""
WecomCardBuilder - 企业微信模板卡片构建器

企业微信使用模板卡片，与飞书的交互卡片不同。
主要限制：
- 最多 2 个按钮
- 固定的模板结构
"""
import json
from typing import Literal

from shared.core.channels import ChannelCard


class WecomCardBuilder:
    """
    企业微信模板卡片构建器

    使用方式:
        card = (
            WecomCardBuilder()
            .set_title("标题")
            .set_description("描述")
            .add_button("确认", "confirm", style=1)
            .add_button("拒绝", "reject", style=2)
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
        """设置主标题"""
        self._title = title
        return self

    def set_description(self, description: str) -> "WecomCardBuilder":
        """设置副标题/描述"""
        self._description = description
        return self

    def set_source(self, desc: str) -> "WecomCardBuilder":
        """设置来源描述"""
        self._source_desc = desc
        return self

    def add_horizontal_content(
        self,
        key: str,
        value: str,
        content_type: int = 0,
    ) -> "WecomCardBuilder":
        """添加横向内容项"""
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
        """添加按钮（最多2个）"""
        if len(self._buttons) >= self.MAX_BUTTONS:
            return self

        self._buttons.append({
            "text": text,
            "style": style,
            "key": key,
        })
        return self

    def build(self) -> dict:
        """构建企微模板卡片"""
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
        """从通用 ChannelCard 转换为企微模板卡片"""
        builder = cls()
        builder.set_title(card.title)

        # 提取描述（第一个 text 元素）
        for element in card.elements:
            if element.element_type == "text" and element.content:
                builder.set_description(element.content)
                break

        # 提取字段
        for element in card.elements:
            if element.element_type == "field" and element.fields:
                for field in element.fields:
                    builder.add_horizontal_content(
                        key=field.get("label", ""),
                        value=field.get("value", "")
                    )

        # 转换按钮
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
