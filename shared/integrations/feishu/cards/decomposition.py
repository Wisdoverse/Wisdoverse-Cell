"""Decomposition approval cards."""
from datetime import UTC, datetime

from .builder import CardBuilder, truncate_card_if_needed

PRIORITY_ICONS = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}


def build_decomposition_approval_card(
    wp_id: int,
    subject: str,
    wbs_result: dict,
) -> dict:
    builder = CardBuilder()
    builder.set_header("\U0001f4ca 任务拆解待审批", template="blue", subtitle=subject)

    builder.add_markdown(f"**摘要**: {wbs_result.get('summary', '')}")
    builder.add_divider()

    subtasks = wbs_result.get("subtasks", [])
    for i, st in enumerate(subtasks, 1):
        icon = PRIORITY_ICONS.get(st.get("priority", "medium"), "\U0001f7e1")
        days = st.get("estimated_days", 0)
        builder.add_markdown(f"{icon} **US{i}**: {st['subject']}  ({days}d)")

        children = st.get("children", [])
        task_lines = []
        for child in children:
            task_lines.append(f"  \u2514 {child['subject']} ({child['estimated_hours']}h)")
        if task_lines:
            builder.add_markdown("\n".join(task_lines))

    builder.add_divider()

    total_stories = len(subtasks)
    total_tasks = sum(len(st.get("children", [])) for st in subtasks)
    builder.add_markdown(f"**共 {total_stories} 个 User Story, {total_tasks} 个 Task**")

    builder.add_action_buttons([
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "\u2713 批准写入 OP"},
            "type": "primary",
            "value": {"action": "approve_decomposition", "wp_id": wp_id},
        },
    ])

    builder.add_input(
        name="reject_reason",
        placeholder="请输入拒绝原因（可选）",
        max_length=200,
    )

    builder.add_action_buttons([
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "\u2717 拒绝"},
            "type": "danger",
            "value": {"action": "reject_decomposition", "wp_id": wp_id},
        },
    ])

    builder.add_note(f"AI 生成，仅供参考 · WP #{wp_id} · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
    return truncate_card_if_needed(builder.build())


def build_decomposition_approved_card(
    wp_id: int,
    subject: str,
    approved_by: str,
    story_count: int,
    task_count: int,
) -> dict:
    builder = CardBuilder()
    builder.set_header("\u2705 任务拆解已批准", template="green", subtitle=subject)
    builder.add_markdown(
        f"**{approved_by}** 已批准写入 OpenProject\n"
        f"共 {story_count} 个 User Story, {task_count} 个 Task"
    )
    builder.add_note(f"AI 生成，仅供参考 · WP #{wp_id} · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
    return truncate_card_if_needed(builder.build())


def build_decomposition_rejected_card(
    wp_id: int,
    subject: str,
    rejected_by: str,
    reason: str = "",
) -> dict:
    builder = CardBuilder()
    builder.set_header("\u274c 任务拆解已拒绝", template="red", subtitle=subject)
    builder.add_markdown(f"**{rejected_by}** 已拒绝此拆解方案")
    if reason:
        builder.add_markdown(f"**拒绝原因：** {reason}")
    builder.add_note(f"AI 生成，仅供参考 · WP #{wp_id} · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
    return truncate_card_if_needed(builder.build())


def build_task_refinement_approval_card(
    wp_id: int,
    subject: str,
    reason: str,
    subtasks: list[dict],
) -> dict:
    builder = CardBuilder()
    builder.set_header("\U0001f50d 任务细化待审批", template="orange", subtitle=subject)

    builder.add_markdown(f"**AI 判断**: {reason}")
    builder.add_divider()

    for i, task in enumerate(subtasks, 1):
        hours = task.get("estimated_hours", 0)
        builder.add_markdown(f"  {i}. {task['subject']} ({hours}h)")

    builder.add_divider()
    builder.add_markdown(f"**共 {len(subtasks)} 个子任务**")

    builder.add_action_buttons([
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "\u2713 批准写入 OP"},
            "type": "primary",
            "value": {"action": "approve_decomposition", "wp_id": wp_id},
        },
    ])

    builder.add_input(
        name="reject_reason",
        placeholder="请输入拒绝原因（可选）",
        max_length=200,
    )

    builder.add_action_buttons([
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "\u2717 拒绝"},
            "type": "danger",
            "value": {"action": "reject_decomposition", "wp_id": wp_id},
        },
    ])

    builder.add_note(f"AI 生成，仅供参考 · WP #{wp_id} · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
    return truncate_card_if_needed(builder.build())
