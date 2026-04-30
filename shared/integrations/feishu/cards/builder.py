"""
CardBuilder - 飞书消息卡片构建器

使用 Builder 模式构建复杂的消息卡片。

使用方式:
    card = (
        CardBuilder()
        .set_header("标题", template="blue")
        .add_text("内容")
        .add_action_buttons([...])
        .build()
    )
"""
import json
from typing import Optional

# Feishu card size limit (25KB)
CARD_SIZE_LIMIT = 25000
_TRUNCATION_NOTE = "...\n\n> 内容过长，已截断。请使用命令查看完整内容。"


def truncate_card_if_needed(card: dict, max_bytes: int = CARD_SIZE_LIMIT) -> dict:
    """Truncate card content if JSON-serialized size exceeds Feishu's limit.

    Strategy:
    1. Try to shorten the longest markdown/text elements progressively.
    2. If still over limit, pop inner elements (keeping the last divider/note).
    3. Append a truncation notice so users know content was cut.
    """
    serialized = json.dumps(card, ensure_ascii=False)
    if len(serialized.encode("utf-8")) <= max_bytes:
        return card

    # Resolve elements list (supports both flat "elements" and nested "body.elements")
    elements = card.get("elements", card.get("body", {}).get("elements", []))

    # Phase 1: shorten longest markdown/text elements
    md_indices = []
    for i, el in enumerate(elements):
        text_obj = el.get("text")
        if text_obj and text_obj.get("tag") in ("lark_md", "plain_text"):
            md_indices.append((i, len(text_obj.get("content", ""))))
    md_indices.sort(key=lambda x: x[1], reverse=True)

    for idx, _ in md_indices:
        content = elements[idx]["text"]["content"]
        while len(json.dumps(card, ensure_ascii=False).encode("utf-8")) > max_bytes and len(content) > 100:
            content = content[: len(content) * 3 // 4]
            elements[idx]["text"]["content"] = content + _TRUNCATION_NOTE
        if len(json.dumps(card, ensure_ascii=False).encode("utf-8")) <= max_bytes:
            return card

    # Phase 2: remove elements from the end (keep last element if it's a note/divider)
    while elements and len(json.dumps(card, ensure_ascii=False).encode("utf-8")) > max_bytes:
        elements.pop(-2 if len(elements) > 1 else -1)

    # Add truncation notice
    elements.append({
        "tag": "markdown",
        "content": _TRUNCATION_NOTE.strip(),
    })

    return card


class CardBuilder:
    """
    飞书消息卡片构建器

    支持链式调用，简化卡片构建。
    """

    def __init__(self):
        self.header: Optional[dict] = None
        self.elements: list[dict] = []
        self.config = {"wide_screen_mode": True}

    def set_header(
        self,
        title: str,
        template: str = "blue",
        subtitle: Optional[str] = None,
    ) -> "CardBuilder":
        """
        设置卡片头部

        Args:
            title: 标题文本
            template: 颜色模板 (blue, green, red, orange, purple, indigo, turquoise, wathet, yellow, grey, carmine, violet)
            subtitle: 副标题（可选）
        """
        self.header = {
            "title": {"tag": "plain_text", "content": title},
            "template": template
        }
        if subtitle:
            self.header["subtitle"] = {"tag": "plain_text", "content": subtitle}
        return self

    def add_text(
        self,
        content: str,
        tag: str = "lark_md",
    ) -> "CardBuilder":
        """
        添加文本元素

        Args:
            content: 文本内容（支持 Markdown）
            tag: 文本类型 (lark_md, plain_text)
        """
        self.elements.append({
            "tag": "div",
            "text": {"tag": tag, "content": content}
        })
        return self

    def add_markdown(self, content: str) -> "CardBuilder":
        """添加 Markdown 文本"""
        return self.add_text(content, tag="lark_md")

    def add_plain_text(self, content: str) -> "CardBuilder":
        """添加纯文本"""
        return self.add_text(content, tag="plain_text")

    def add_input(
        self,
        name: str,
        placeholder: str = "",
        max_length: int = 200,
    ) -> "CardBuilder":
        """
        添加文本输入框

        Args:
            name: 输入框名称（用于 form_value 提取）
            placeholder: 占位提示文本
            max_length: 最大输入长度
        """
        self.elements.append({
            "tag": "input",
            "name": name,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "max_length": max_length,
        })
        return self

    def add_action_buttons(self, buttons: list[dict]) -> "CardBuilder":
        """
        添加操作按钮组

        Args:
            buttons: 按钮列表，每个按钮包含 tag, text, type, value
        """
        self.elements.append({
            "tag": "action",
            "actions": buttons
        })
        return self

    def add_button(
        self,
        text: str,
        value: dict,
        button_type: str = "default",
    ) -> "CardBuilder":
        """
        添加单个按钮（会自动放入 action 组）

        Args:
            text: 按钮文本
            value: 点击时传递的值
            button_type: 按钮类型 (default, primary, danger)
        """
        button = {
            "tag": "button",
            "text": {"tag": "plain_text", "content": text},
            "type": button_type,
            "value": value
        }

        # 如果最后一个元素是 action，追加到里面
        if self.elements and self.elements[-1].get("tag") == "action":
            self.elements[-1]["actions"].append(button)
        else:
            self.add_action_buttons([button])

        return self

    def add_divider(self) -> "CardBuilder":
        """添加分割线"""
        self.elements.append({"tag": "hr"})
        return self

    def add_note(self, text: str) -> "CardBuilder":
        """添加备注"""
        self.elements.append({
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": text}
            ]
        })
        return self

    def add_fields(self, fields: list[tuple[str, str]], is_short: bool = True) -> "CardBuilder":
        """
        添加字段组

        Args:
            fields: (标题, 内容) 元组列表
            is_short: 是否短字段（两列显示）
        """
        field_elements = []
        for title, content in fields:
            field_elements.append({
                "is_short": is_short,
                "text": {
                    "tag": "lark_md",
                    "content": f"**{title}**\n{content}"
                }
            })

        self.elements.append({
            "tag": "div",
            "fields": field_elements
        })
        return self

    def build(self) -> dict:
        """构建最终的卡片 JSON"""
        card = {
            "config": self.config,
            "elements": self.elements
        }

        if self.header:
            card["header"] = self.header

        return card

    def build_message(self) -> dict:
        """构建完整的消息体（包含 msg_type）"""
        return {
            "msg_type": "interactive",
            "card": self.build()
        }
