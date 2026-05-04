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

    def build_bitable_operation_expired(self, *, operation: str) -> dict[str, Any]:
        return (
            CardBuilder()
            .set_header("⚠️ 操作已过期", template="red")
            .add_markdown(f"此操作已过期（超过30分钟），请重新发起{operation}。")
            .build()
        )

    def build_bitable_update_success(
        self,
        *,
        record_id: str,
        field_lines: str,
    ) -> dict[str, Any]:
        return (
            CardBuilder()
            .set_header("✅ 表格已更新", template="green")
            .add_markdown(f"**记录 ID**: `{record_id}`\n\n**已修改内容**:\n{field_lines}")
            .add_note("修改已生效")
            .build()
        )

    def build_bitable_update_failure(self, *, record_id: str) -> dict[str, Any]:
        return (
            CardBuilder()
            .set_header("⚠️ 更新失败", template="red")
            .add_markdown(f"记录 `{record_id}` 更新失败，请稍后重试或联系管理员")
            .build()
        )

    def build_bitable_create_success(
        self,
        *,
        record_id: str,
        field_lines: str,
    ) -> dict[str, Any]:
        return (
            CardBuilder()
            .set_header("✅ 任务已创建", template="green")
            .add_markdown(f"**记录 ID**: `{record_id}`\n\n**任务内容**:\n{field_lines}")
            .add_note("已写入飞书表格")
            .build()
        )

    def build_bitable_create_failure(self) -> dict[str, Any]:
        return (
            CardBuilder()
            .set_header("⚠️ 创建失败", template="red")
            .add_markdown("创建失败，请稍后重试或联系管理员")
            .build()
        )

    def build_bitable_rejection(self, *, action_type: str) -> dict[str, Any]:
        if action_type == "create":
            title = "🚫 已取消创建"
            text = "用户已取消此次任务创建。"
        else:
            title = "🚫 已取消修改"
            text = "用户已取消此次表格修改。"
        return CardBuilder().set_header(title, template="grey").add_markdown(text).build()

    def build_ai_reply_card(self, *, reply: str, elapsed: float) -> dict[str, Any]:
        return (
            CardBuilder()
            .set_header("🤖 项目经理", template="blue")
            .add_markdown(reply)
            .add_divider()
            .add_note(f"⏱ {elapsed:.1f}s · AI 生成，仅供参考 · Wisdoverse Cell")
            .build()
        )
