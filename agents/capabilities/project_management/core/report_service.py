"""Report Service - 生成日报/周报并推送到飞书"""

from datetime import date, datetime, timezone

from shared.config import settings
from shared.integrations.feishu.bitable import BitableService
from shared.integrations.feishu.cards.builder import CardBuilder
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import OpenProjectClient, get_op_client
from shared.utils.logger import get_logger

logger = get_logger("pjm_agent.report")

_DONE_STATUSES = {"closed", "done", "resolved", "已完成", "complete", "finished", "rejected"}


class ReportService:
    def __init__(
        self,
        op_client: OpenProjectClient | None = None,
        bitable: BitableService | None = None,
    ):
        self._op = op_client or get_op_client()
        self._bitable = bitable or BitableService()

    async def _fetch_op_work_packages(self) -> list[dict]:
        if not settings.decompose_project_ids.strip():
            return []
        project_ids = [p.strip() for p in settings.decompose_project_ids.split(",") if p.strip()]
        wps = []
        for pid in project_ids:
            try:
                items = await self._op.get_work_packages(project_id=int(pid))
                wps.extend(items)
            except Exception as e:
                logger.error("report_fetch_wp_failed", project_id=pid, error=str(e))
        return wps

    async def _fetch_feishu_tasks(self) -> list[dict]:
        app_token = settings.feishu_pm_app_token
        table_id = settings.feishu_pm_task_table_id
        if not app_token or not table_id:
            logger.warning("fetch_feishu_tasks_missing_config")
            return []
        records = await self._bitable.list_all_records(
            app_token=app_token, table_id=table_id,
        )
        return [r.get("fields", {}) for r in records]

    def _extract_wp_fields(self, wp: dict) -> dict:
        links = wp.get("_links", {})
        return {
            "id": wp.get("id"),
            "subject": wp.get("subject", ""),
            "progress": wp.get("percentageDone", 0) or 0,
            "due_date": wp.get("dueDate"),
            "status": links.get("status", {}).get("title", ""),
            "project": links.get("project", {}).get("title", ""),
            "assignee": links.get("assignee", {}).get("title", "") or "未分配",
        }

    def _aggregate(
        self, wps: list[dict], feishu_tasks: list[dict],
    ) -> dict:
        today = date.today().isoformat()
        by_status: dict[str, int] = {}
        by_project: dict[str, dict] = {}
        by_assignee: dict[str, dict] = {}
        overdue: list[dict] = []
        progress_sum = 0

        # OP 任务统计
        for wp in wps:
            status = wp["status"]
            project = wp["project"]
            assignee = wp["assignee"]
            progress = wp["progress"]

            by_status[status] = by_status.get(status, 0) + 1

            if project not in by_project:
                by_project[project] = {
                    "total": 0, "by_status": {}, "source": "op",
                }
            by_project[project]["total"] += 1
            bp = by_project[project]["by_status"]
            bp[status] = bp.get(status, 0) + 1

            if assignee not in by_assignee:
                by_assignee[assignee] = {
                    "total": 0, "progress_sum": 0, "by_status": {},
                }
            by_assignee[assignee]["total"] += 1
            by_assignee[assignee]["progress_sum"] += progress
            ba = by_assignee[assignee]["by_status"]
            ba[status] = ba.get(status, 0) + 1

            progress_sum += progress

            due = wp.get("due_date")
            if (
                due and due < today
                and status.lower() not in _DONE_STATUSES
                and progress < 100
            ):
                overdue.append(wp)

        # 飞书任务纳入主统计
        for t in feishu_tasks:
            status = t.get("状态", "未知")
            progress = t.get("进度") or 0
            if isinstance(progress, str):
                try:
                    progress = int(progress.rstrip("%"))
                except ValueError:
                    progress = 0

            dri = t.get("DRI (负责人)", "")
            if isinstance(dri, list) and dri:
                assignee = (
                    dri[0].get("text", "未分配")
                    if isinstance(dri[0], dict) else str(dri[0])
                )
            elif isinstance(dri, str):
                assignee = dri or "未分配"
            else:
                assignee = "未分配"

            category = t.get("所属大类", "飞书任务")
            if isinstance(category, list) and category:
                category = (
                    category[0].get("text", "飞书任务")
                    if isinstance(category[0], dict)
                    else str(category[0])
                )
            category = category or "飞书任务"

            by_status[status] = by_status.get(status, 0) + 1

            if category not in by_project:
                by_project[category] = {
                    "total": 0, "by_status": {}, "source": "feishu",
                }
            by_project[category]["total"] += 1
            bp = by_project[category]["by_status"]
            bp[status] = bp.get(status, 0) + 1

            if assignee not in by_assignee:
                by_assignee[assignee] = {
                    "total": 0, "progress_sum": 0, "by_status": {},
                }
            by_assignee[assignee]["total"] += 1
            by_assignee[assignee]["progress_sum"] += progress
            ba = by_assignee[assignee]["by_status"]
            ba[status] = ba.get(status, 0) + 1

            progress_sum += progress

            due_ts = t.get("计划完成日期")
            if due_ts:
                try:
                    due_date = date.fromtimestamp(
                        int(due_ts) / 1000,
                    ).isoformat()
                    if (
                        due_date < today
                        and status not in _DONE_STATUSES
                        and progress < 100
                    ):
                        overdue.append({
                            "id": None,
                            "subject": t.get("任务(动宾短语)", ""),
                            "assignee": assignee,
                            "due_date": due_date,
                            "status": status,
                            "source": "feishu",
                        })
                except (ValueError, TypeError):
                    pass

        total = len(wps) + len(feishu_tasks)
        return {
            "total": total,
            "op_total": len(wps),
            "feishu_total": len(feishu_tasks),
            "by_status": by_status,
            "by_project": by_project,
            "by_assignee": by_assignee,
            "overdue": overdue[:10],
            "avg_progress": round(progress_sum / total) if total > 0 else 0,
        }

    def _build_daily_card(self, stats: dict) -> dict:
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

        total_label = (
            f"{total} (OP:{op_total} + 飞书:{feishu_total})"
        )
        builder = (
            CardBuilder()
            .set_header(f"📋 项目日报 ({today})", template="blue")
            .add_fields([
                ("任务总数", total_label),
                ("平均进度", f"{avg}%"),
                ("进行中", str(in_progress)),
                ("已完成", str(done)),
            ])
        )

        overdue_count = len(stats["overdue"])
        if overdue_count > 0:
            builder.add_markdown(f"⚠️ **逾期任务**: {overdue_count} 个")

        if by_project:
            builder.add_divider().add_markdown("**按大类统计**")
            lines = []
            for proj, data in by_project.items():
                in_p = data["by_status"].get(
                    "进行中", data["by_status"].get("In Progress", 0),
                )
                done_p = data["by_status"].get(
                    "已完成",
                    data["by_status"].get(
                        "Done", data["by_status"].get("Closed", 0),
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

    def _build_weekly_card(self, stats: dict) -> dict:
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

        total_label = (
            f"{total} (OP:{op_total} + 飞书:{feishu_total})"
        )
        builder = (
            CardBuilder()
            .set_header(f"📊 项目周报 ({today})", template="purple")
            .add_fields([
                ("任务总数", total_label),
                ("平均进度", f"{avg}%"),
                ("进行中", str(in_progress)),
                ("已完成", str(done)),
            ])
        )

        overdue_count = len(stats["overdue"])
        if overdue_count > 0:
            builder.add_markdown(f"⚠️ **逾期任务**: {overdue_count} 个")

        if by_project:
            builder.add_divider().add_markdown("**按大类统计**")
            lines = []
            for proj, data in by_project.items():
                in_p = data["by_status"].get(
                    "进行中", data["by_status"].get("In Progress", 0),
                )
                done_p = data["by_status"].get(
                    "已完成",
                    data["by_status"].get(
                        "Done", data["by_status"].get("Closed", 0),
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
                    "进行中", data["by_status"].get("In Progress", 0),
                )
                done_p = data["by_status"].get(
                    "已完成",
                    data["by_status"].get(
                        "Done", data["by_status"].get("Closed", 0),
                    ),
                )
                avg_p = (
                    round(data["progress_sum"] / data["total"])
                    if data["total"] > 0 else 0
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

    async def generate_daily(self) -> dict:
        wps_raw = await self._fetch_op_work_packages()
        wps = [self._extract_wp_fields(wp) for wp in wps_raw]
        feishu_tasks = await self._fetch_feishu_tasks()
        stats = self._aggregate(wps, feishu_tasks)
        return {"card": self._build_daily_card(stats), "stats": stats}

    async def generate_weekly(self) -> dict:
        wps_raw = await self._fetch_op_work_packages()
        wps = [self._extract_wp_fields(wp) for wp in wps_raw]
        feishu_tasks = await self._fetch_feishu_tasks()
        stats = self._aggregate(wps, feishu_tasks)
        return {"card": self._build_weekly_card(stats), "stats": stats}

    async def push_card(self, card: dict) -> None:
        chat_id = settings.feishu_report_chat_id
        if not chat_id:
            logger.warning("report_push_skipped", reason="feishu_report_chat_id_not_set")
            return
        feishu = get_feishu_client()
        id_type = "open_id" if chat_id.startswith("ou_") else "chat_id"
        await feishu.send_card(receive_id=chat_id, receive_id_type=id_type, card=card)
        logger.info("report_card_pushed", chat_id=chat_id)
