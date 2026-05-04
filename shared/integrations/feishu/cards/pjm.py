"""Feishu card renderer adapter for PJM workflows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from shared.integrations.feishu.cards.builder import CardBuilder
from shared.integrations.feishu.cards.decomposition import (
    build_decomposition_approval_card,
    build_task_refinement_approval_card,
)


class FeishuPJMCardRenderer:
    """Render PJM card payloads using Feishu's interactive-card schema."""

    def build_daily_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        today = date.today().strftime("%Y-%m-%d")
        total = stats["total"]
        avg = stats["avg_progress"]
        by_status = stats["by_status"]
        by_project = stats["by_project"]
        overdue = stats["overdue"]
        op_total = stats.get("op_total", 0)
        feishu_total = stats.get("feishu_total", 0)

        in_progress = by_status.get("进行中", by_status.get("In Progress", 0))
        done = by_status.get("已完成", by_status.get("Done", by_status.get("Closed", 0)))

        total_label = f"{total} (OP:{op_total} + 飞书:{feishu_total})"
        builder = (
            CardBuilder()
            .set_header(f"📋 项目日报 ({today})", template="blue")
            .add_fields(
                [
                    ("任务总数", total_label),
                    ("平均进度", f"{avg}%"),
                    ("进行中", str(in_progress)),
                    ("已完成", str(done)),
                ]
            )
        )

        overdue_count = len(stats["overdue"])
        if overdue_count > 0:
            builder.add_markdown(f"⚠️ **逾期任务**: {overdue_count} 个")

        if by_project:
            builder.add_divider().add_markdown("**按大类统计**")
            lines = []
            for proj, data in by_project.items():
                in_p = data["by_status"].get(
                    "进行中",
                    data["by_status"].get("In Progress", 0),
                )
                done_p = data["by_status"].get(
                    "已完成",
                    data["by_status"].get(
                        "Done",
                        data["by_status"].get("Closed", 0),
                    ),
                )
                source = "🔵" if data.get("source") == "op" else "🟢"
                lines.append(
                    f"{source} **{proj}**: {data['total']} 个"
                    f" ({in_p} 进行中, {done_p} 已完成)"
                )
            builder.add_markdown("\n".join(lines))

        if overdue:
            builder.add_divider().add_markdown(
                f"**逾期任务** ({len(overdue)} 个)",
            )
            lines = []
            for wp in overdue:
                prefix = f"WP#{wp['id']}" if wp.get("id") else "飞书"
                lines.append(
                    f"- {prefix} {wp['subject']} "
                    f"({wp['assignee']}, 截止 {wp.get('due_date', '')})"
                )
            builder.add_markdown("\n".join(lines))

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        builder.add_divider().add_note(f"PJM Agent | {now_str}")
        return builder.build()

    def build_weekly_report_card(self, stats: dict[str, Any]) -> dict[str, Any]:
        today = date.today().strftime("%Y-%m-%d")
        total = stats["total"]
        avg = stats["avg_progress"]
        by_status = stats["by_status"]
        by_project = stats["by_project"]
        by_assignee = stats["by_assignee"]
        overdue = stats["overdue"]
        op_total = stats.get("op_total", 0)
        feishu_total = stats.get("feishu_total", 0)

        in_progress = by_status.get("进行中", by_status.get("In Progress", 0))
        done = by_status.get("已完成", by_status.get("Done", by_status.get("Closed", 0)))

        total_label = f"{total} (OP:{op_total} + 飞书:{feishu_total})"
        builder = (
            CardBuilder()
            .set_header(f"📊 项目周报 ({today})", template="purple")
            .add_fields(
                [
                    ("任务总数", total_label),
                    ("平均进度", f"{avg}%"),
                    ("进行中", str(in_progress)),
                    ("已完成", str(done)),
                ]
            )
        )

        overdue_count = len(stats["overdue"])
        if overdue_count > 0:
            builder.add_markdown(f"⚠️ **逾期任务**: {overdue_count} 个")

        if by_project:
            builder.add_divider().add_markdown("**按大类统计**")
            lines = []
            for proj, data in by_project.items():
                in_p = data["by_status"].get(
                    "进行中",
                    data["by_status"].get("In Progress", 0),
                )
                done_p = data["by_status"].get(
                    "已完成",
                    data["by_status"].get(
                        "Done",
                        data["by_status"].get("Closed", 0),
                    ),
                )
                source = "🔵" if data.get("source") == "op" else "🟢"
                lines.append(
                    f"{source} **{proj}**: {data['total']} 个"
                    f" ({in_p} 进行中, {done_p} 已完成)"
                )
            builder.add_markdown("\n".join(lines))

        if by_assignee:
            builder.add_divider().add_markdown("**按负责人统计**")
            lines = []
            for name, data in by_assignee.items():
                in_p = data["by_status"].get(
                    "进行中",
                    data["by_status"].get("In Progress", 0),
                )
                done_p = data["by_status"].get(
                    "已完成",
                    data["by_status"].get(
                        "Done",
                        data["by_status"].get("Closed", 0),
                    ),
                )
                avg_p = (
                    round(data["progress_sum"] / data["total"])
                    if data["total"] > 0
                    else 0
                )
                lines.append(
                    f"**{name}**: {data['total']} 个 "
                    f"({in_p} 进行中, {done_p} 已完成, 均进度 {avg_p}%)"
                )
            builder.add_markdown("\n".join(lines))

        if overdue:
            builder.add_divider().add_markdown(
                f"**逾期任务** ({len(overdue)} 个)",
            )
            lines = []
            for wp in overdue:
                prefix = f"WP#{wp['id']}" if wp.get("id") else "飞书"
                lines.append(
                    f"- {prefix} {wp['subject']} "
                    f"({wp['assignee']}, 截止 {wp.get('due_date', '')})"
                )
            builder.add_markdown("\n".join(lines))

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        builder.add_divider().add_note(f"PJM Agent | {now_str}")
        return builder.build()

    def build_decomposition_approval_card(
        self,
        wp_id: int,
        subject: str,
        wbs_result: dict[str, Any],
    ) -> dict[str, Any]:
        return build_decomposition_approval_card(
            wp_id=wp_id,
            subject=subject,
            wbs_result=wbs_result,
        )

    def build_task_refinement_approval_card(
        self,
        wp_id: int,
        subject: str,
        reason: str,
        subtasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return build_task_refinement_approval_card(
            wp_id=wp_id,
            subject=subject,
            reason=reason,
            subtasks=subtasks,
        )
