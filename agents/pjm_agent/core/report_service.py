"""Generate PJM daily and weekly reports."""

from datetime import date

from shared.config import settings
from shared.core import BitableTablePort, FeishuMessengerPort, OpenProjectWorkPackagePort
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .card_ports import PJMCardRendererPort

logger = get_logger("pjm_agent.report")

_DONE_STATUSES = {"closed", "done", "resolved", "已完成", "complete", "finished", "rejected"}


class ReportService:
    def __init__(
        self,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
        *,
        card_renderer: PJMCardRendererPort,
        messenger: FeishuMessengerPort | None = None,
    ):
        self._op = op_client
        self._bitable = bitable
        self._card_renderer = card_renderer
        self._messenger = messenger

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

        # OpenProject task stats.
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

        # Include Feishu tasks in the aggregate operator report.
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

    async def generate_daily(self) -> dict:
        wps_raw = await self._fetch_op_work_packages()
        wps = [self._extract_wp_fields(wp) for wp in wps_raw]
        feishu_tasks = await self._fetch_feishu_tasks()
        stats = self._aggregate(wps, feishu_tasks)
        return {
            "card": self._card_renderer.build_daily_report_card(stats),
            "stats": stats,
        }

    async def generate_weekly(self) -> dict:
        wps_raw = await self._fetch_op_work_packages()
        wps = [self._extract_wp_fields(wp) for wp in wps_raw]
        feishu_tasks = await self._fetch_feishu_tasks()
        stats = self._aggregate(wps, feishu_tasks)
        return {
            "card": self._card_renderer.build_weekly_report_card(stats),
            "stats": stats,
        }

    async def push_card(self, card: dict) -> None:
        chat_id = settings.feishu_report_chat_id
        if not chat_id:
            logger.warning("report_push_skipped", reason="feishu_report_chat_id_not_set")
            return
        if self._messenger is None:
            logger.warning("report_push_skipped", reason="messenger_port_not_configured")
            return
        id_type = "open_id" if chat_id.startswith("ou_") else "chat_id"
        await self._messenger.send_card(receive_id=chat_id, receive_id_type=id_type, card=card)
        logger.info("report_card_pushed", chat_hash=hash_identifier(chat_id))
