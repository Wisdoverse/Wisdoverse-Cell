"""
Requirement Cards - 需求相关的消息卡片

包含：
- 需求提取结果卡片
- 需求确认卡片
- 需求拒绝卡片
"""
from datetime import UTC, datetime
from typing import Optional

from .builder import CardBuilder

PRIORITY_ICONS = {
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}

PRIORITY_COLORS = {
    "HIGH": "red",
    "MEDIUM": "orange",
    "LOW": "green",
}


def build_requirement_extracted_card(
    requirements: list[dict],
    meeting_title: str = "",
    questions_count: int = 0,
    detail_url: Optional[str] = None,
) -> dict:
    """
    构建需求提取结果卡片

    Args:
        requirements: 需求列表 [{id, title, description, priority, category}]
        meeting_title: 会议标题
        questions_count: 待确认问题数量
        detail_url: 详情页 URL
    """
    count = len(requirements)
    builder = CardBuilder()

    # Header
    title = f"📋 提取了 {count} 个新需求"
    if meeting_title:
        builder.set_header(title, template="blue", subtitle=meeting_title)
    else:
        builder.set_header(title, template="blue")

    # Each requirement
    for req in requirements:
        priority = req.get("priority", "MEDIUM")
        icon = PRIORITY_ICONS.get(priority, "🟡")
        category = req.get("category", "")

        # Title line
        builder.add_markdown(
            f"**{req['title']}** {icon} {priority}"
            + (f" | {category}" if category else "")
        )

        # Description (truncated)
        desc = req.get("description", "")
        if len(desc) > 80:
            desc = desc[:80] + "..."
        if desc:
            builder.add_plain_text(desc)

        # Action buttons
        builder.add_action_buttons([
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✓ 确认"},
                "type": "primary",
                "value": {"action": "confirm_requirement", "req_id": req["id"]}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✗ 拒绝"},
                "type": "danger",
                "value": {"action": "reject_requirement", "req_id": req["id"]}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📄 详情"},
                "type": "default",
                "value": {"action": "view_detail", "req_id": req["id"]}
            },
        ])

        builder.add_divider()

    # Questions summary
    if questions_count > 0:
        builder.add_markdown(f"⚠️ **待确认问题** ({questions_count})")

    # Footer buttons
    footer_buttons = []
    if detail_url:
        footer_buttons.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "🔗 打开面板"},
            "type": "default",
            "url": detail_url
        })

    if footer_buttons:
        builder.add_action_buttons(footer_buttons)

    return builder.build()


def build_requirement_confirmed_card(
    requirement: dict,
    confirmed_by: str,
    confirmed_at: Optional[datetime] = None,
) -> dict:
    """
    构建需求确认卡片

    用于替换原卡片，显示确认状态。
    """
    builder = CardBuilder()

    builder.set_header("✅ 需求已确认", template="green")

    priority = requirement.get("priority", "MEDIUM")
    icon = PRIORITY_ICONS.get(priority, "🟡")

    builder.add_markdown(f"**{requirement['title']}** {icon} {priority}")

    desc = requirement.get("description", "")
    if desc:
        if len(desc) > 100:
            desc = desc[:100] + "..."
        builder.add_plain_text(desc)

    builder.add_divider()

    # Confirmation info
    time_str = (confirmed_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M")
    builder.add_note(f"✓ 由 {confirmed_by} 确认于 {time_str}")

    return builder.build()


def build_requirement_rejected_card(
    requirement: dict,
    rejected_by: str,
    reason: str,
    rejected_at: Optional[datetime] = None,
) -> dict:
    """
    构建需求拒绝卡片

    用于替换原卡片，显示拒绝状态。
    """
    builder = CardBuilder()

    builder.set_header("❌ 需求已拒绝", template="red")

    builder.add_markdown(f"**{requirement['title']}**")

    builder.add_divider()

    # Rejection info
    builder.add_markdown(f"**拒绝原因：** {reason}")

    time_str = (rejected_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M")
    builder.add_note(f"✗ 由 {rejected_by} 拒绝于 {time_str}")

    return builder.build()


def build_requirement_detail_card(
    requirement: dict,
    meeting: Optional[dict] = None,
) -> dict:
    """
    构建需求详情卡片

    显示需求的完整信息，包括来源引用和会议信息。

    Args:
        requirement: 需求数据 {id, title, description, priority, category, source_quote, status}
        meeting: 会议数据 {id, title, meeting_date, participants}
    """
    builder = CardBuilder()

    # Header with status icon
    status = requirement.get("status", "pending")
    status_icons = {
        "pending": "⏳",
        "confirmed": "✅",
        "rejected": "❌",
    }
    status_icon = status_icons.get(status, "⏳")
    builder.set_header(f"{status_icon} 需求详情", template="blue")

    # Basic info
    priority = requirement.get("priority", "MEDIUM")
    icon = PRIORITY_ICONS.get(priority, "🟡")
    category = requirement.get("category", "")

    builder.add_markdown(f"**{requirement.get('title', '未命名需求')}**")
    builder.add_markdown(f"{icon} {priority}" + (f" | 📁 {category}" if category else ""))

    builder.add_divider()

    # Description
    desc = requirement.get("description", "")
    if desc:
        builder.add_markdown("**📝 需求描述**")
        builder.add_plain_text(desc)
        builder.add_divider()

    # Source quote - 来源引用
    source_quote = requirement.get("source_quote")
    if source_quote:
        builder.add_markdown("**💬 原文引用**")
        builder.add_markdown(f"> {source_quote}")
        builder.add_divider()

    # Meeting info - 会议来源
    if meeting:
        builder.add_markdown("**📅 来源会议**")
        meeting_title = meeting.get("title", "未命名会议")
        meeting_date = meeting.get("meeting_date")
        participants = meeting.get("participants", [])

        info_lines = [f"• **会议**: {meeting_title}"]
        if meeting_date:
            info_lines.append(f"• **时间**: {meeting_date}")
        if participants:
            info_lines.append(f"• **参与者**: {', '.join(participants[:5])}")

        builder.add_markdown("\n".join(info_lines))

    # Footer note
    req_id = requirement.get("id", "")
    builder.add_note(f"需求 ID: {req_id}")

    return builder.build()


def build_bot_help_card() -> dict:
    """构建 Bot 帮助卡片"""
    builder = CardBuilder()

    builder.set_header("🤖 需求管理助手", template="blue")

    builder.add_markdown("""**使用方式：**

• 直接发送会议内容 → 自动提取需求
• `/list` → 查看待确认需求
• `/export` → 导出 PRD 文档
• `/help` → 显示此帮助""")

    return builder.build()


def build_requirement_list_card(
    requirements: list[dict],
    page: int = 1,
    total_pages: int = 1,
    total_count: int = 0,
    chat_id: str = "",
) -> dict:
    """
    构建待确认需求列表卡片

    Args:
        requirements: 需求列表 [{id, title, description, priority, category}]
        page: 当前页码
        total_pages: 总页数
        total_count: 需求总数
        chat_id: 聊天ID (用于分页回调)
    """
    builder = CardBuilder()

    # Header with count
    builder.set_header(
        f"📋 待确认需求 ({total_count})",
        template="blue",
        subtitle=f"第 {page}/{total_pages} 页" if total_pages > 1 else None
    )

    if not requirements:
        builder.add_markdown("✅ **暂无待确认需求**\n\n所有需求已处理完毕。")
        return builder.build()

    # Each requirement
    for req in requirements:
        priority = req.get("priority", "MEDIUM")
        icon = PRIORITY_ICONS.get(priority, "🟡")
        category = req.get("category", "")

        # Title line with priority and category
        title_line = f"**{req['title']}** {icon}"
        if category:
            title_line += f" | {category}"
        builder.add_markdown(title_line)

        # Description (truncated)
        desc = req.get("description", "")
        if len(desc) > 60:
            desc = desc[:60] + "..."
        if desc:
            builder.add_plain_text(desc)

        # Action buttons for this requirement
        builder.add_action_buttons([
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✓ 确认"},
                "type": "primary",
                "value": {
                    "action": "list_confirm_requirement",
                    "req_id": req["id"],
                    "page": page,
                    "chat_id": chat_id
                }
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✗ 拒绝"},
                "type": "danger",
                "value": {
                    "action": "list_reject_requirement",
                    "req_id": req["id"],
                    "page": page,
                    "chat_id": chat_id
                }
            },
        ])

        builder.add_divider()

    # Pagination buttons
    if total_pages > 1:
        pagination_buttons = []

        if page > 1:
            pagination_buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "◀ 上一页"},
                "type": "default",
                "value": {
                    "action": "list_prev_page",
                    "page": page - 1,
                    "chat_id": chat_id
                }
            })

        if page < total_pages:
            pagination_buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "下一页 ▶"},
                "type": "default",
                "value": {
                    "action": "list_next_page",
                    "page": page + 1,
                    "chat_id": chat_id
                }
            })

        if pagination_buttons:
            builder.add_action_buttons(pagination_buttons)

    # Footer note
    builder.add_note(f"共 {total_count} 个待确认需求")

    return builder.build()


def build_prd_preview_card(
    prd_content: str,
    requirements_count: int = 0,
    generated_at: Optional[datetime] = None,
) -> dict:
    """
    构建 PRD 预览卡片

    Args:
        prd_content: PRD 内容（截取前500字符显示）
        requirements_count: 需求数量
        generated_at: 生成时间
    """
    builder = CardBuilder()

    builder.set_header("📄 PRD 文档已生成", template="green")

    # Summary
    time_str = (generated_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M")
    builder.add_markdown(f"**已确认需求数**: {requirements_count}\n**生成时间**: {time_str}")

    builder.add_divider()

    # Preview content (truncated)
    preview = prd_content
    if len(preview) > 500:
        preview = preview[:500] + "\n\n... (内容过长，已截断)"
    builder.add_plain_text(preview)

    builder.add_divider()

    builder.add_note("完整文档可通过 Web 面板下载")

    return builder.build()


def build_calendar_reminder_card(
    event_title: str,
    start_time: str,
    organizer: str = "",
    attendees: list[str] = None,
    keywords_found: list[str] = None,
) -> dict:
    """
    构建日历会议提醒卡片

    Args:
        event_title: 会议标题
        start_time: 开始时间
        organizer: 组织者
        attendees: 参与者列表
        keywords_found: 匹配到的关键词
    """
    builder = CardBuilder()

    builder.set_header("📅 需求相关会议即将开始", template="orange")

    builder.add_markdown(f"**{event_title}**")
    builder.add_markdown(f"⏰ 开始时间: {start_time}")

    if organizer:
        builder.add_markdown(f"👤 组织者: {organizer}")

    if attendees:
        attendees_str = ", ".join(attendees[:5])
        if len(attendees) > 5:
            attendees_str += f" 等 {len(attendees)} 人"
        builder.add_markdown(f"👥 参与者: {attendees_str}")

    if keywords_found:
        builder.add_divider()
        builder.add_markdown(f"🔍 关键词匹配: {', '.join(keywords_found)}")

    builder.add_divider()
    builder.add_note("会议结束后将自动提取需求")

    return builder.build()


def build_batch_confirmation_card(
    requirements: list[dict],
    chat_id: str = "",
) -> dict:
    """
    构建批量确认卡片

    支持一键确认/拒绝多个需求。

    Args:
        requirements: 需求列表 [{id, title, description, priority, category}]
        chat_id: 聊天ID (用于回调)
    """
    count = len(requirements)
    builder = CardBuilder()

    # Header
    builder.set_header(f"📋 批量确认 ({count} 个需求)", template="blue")

    # Requirements list (compact view)
    for idx, req in enumerate(requirements[:10], 1):  # Max 10 items
        priority = req.get("priority", "MEDIUM")
        icon = PRIORITY_ICONS.get(priority, "🟡")
        title = req.get("title", "")
        if len(title) > 30:
            title = title[:30] + "..."
        builder.add_markdown(f"{idx}. **{title}** {icon}")

    if count > 10:
        builder.add_note(f"... 还有 {count - 10} 个需求")

    builder.add_divider()

    # Collect all requirement IDs, skip entries without id
    req_ids = [req["id"] for req in requirements if "id" in req]

    # Batch action buttons
    builder.add_action_buttons([
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "✓ 全部确认"},
            "type": "primary",
            "value": {
                "action": "batch_confirm_all",
                "req_ids": req_ids,
                "chat_id": chat_id
            }
        },
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "✗ 全部拒绝"},
            "type": "danger",
            "value": {
                "action": "batch_reject_all",
                "req_ids": req_ids,
                "chat_id": chat_id
            }
        },
    ])

    builder.add_note(f"共 {count} 个待确认需求")

    return builder.build()


def build_batch_result_card(
    action_type: str,
    success_count: int,
    failed_count: int,
    operator_name: str,
) -> dict:
    """
    构建批量操作结果卡片

    Args:
        action_type: 操作类型 ("confirm" or "reject")
        success_count: 成功数量
        failed_count: 失败数量
        operator_name: 操作者名称
    """
    builder = CardBuilder()

    if action_type == "confirm":
        builder.set_header("✅ 批量确认完成", template="green")
    else:
        builder.set_header("❌ 批量拒绝完成", template="red")

    total = success_count + failed_count
    builder.add_markdown(f"**操作者**: {operator_name}")
    builder.add_markdown(f"**处理结果**: {success_count}/{total} 成功")

    if failed_count > 0:
        builder.add_markdown(f"⚠️ {failed_count} 个需求处理失败")

    time_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    builder.add_note(f"操作时间: {time_str}")

    return builder.build()
