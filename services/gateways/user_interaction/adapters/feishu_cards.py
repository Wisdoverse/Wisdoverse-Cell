"""Feishu card renderer adapter for user-interaction tools."""

from __future__ import annotations

from typing import Any

from shared.integrations.feishu.cards.builder import CardBuilder, truncate_card_if_needed


class FeishuToolCardRenderer:
    """Render tool confirmation cards using Feishu's interactive-card schema."""

    def build_bitable_update_confirmation(
        self,
        *,
        title: str,
        record_id: str,
        field_lines: str,
        action_id: str,
        is_group_chat: bool,
    ) -> dict[str, Any]:
        action_value = {
            "action": "confirm_bitable_update",
            "action_id": action_id,
        }
        builder = (
            CardBuilder()
            .set_header("📝 表格修改确认", template="orange")
            .add_markdown(f"**{title or record_id}**\n\n**修改内容**:\n{field_lines}")
            .add_divider()
            .add_action_buttons(
                [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✓ 确认修改"},
                        "type": "primary",
                        "value": action_value,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✗ 取消"},
                        "type": "danger",
                        "value": {
                            "action": "reject_bitable_update",
                        },
                    },
                ]
            )
        )
        if is_group_chat:
            builder.add_note("仅提议人可操作此卡片")
        builder.add_note("点击按钮确认或取消此修改")
        return truncate_card_if_needed(builder.build())

    def build_bitable_create_confirmation(
        self,
        *,
        field_lines: str,
        action_id: str,
        is_group_chat: bool,
    ) -> dict[str, Any]:
        action_value = {
            "action": "confirm_bitable_create",
            "action_id": action_id,
        }
        builder = (
            CardBuilder()
            .set_header("📋 新建任务确认", template="blue")
            .add_markdown(f"**新任务内容**:\n{field_lines}")
            .add_divider()
            .add_action_buttons(
                [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✓ 确认创建"},
                        "type": "primary",
                        "value": action_value,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✗ 取消"},
                        "type": "danger",
                        "value": {
                            "action": "reject_bitable_create",
                        },
                    },
                ]
            )
        )
        if is_group_chat:
            builder.add_note("仅提议人可操作此卡片")
        builder.add_note("点击按钮确认或取消创建")
        return truncate_card_if_needed(builder.build())
