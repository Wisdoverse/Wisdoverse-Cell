"""里程碑风险检查器"""
import json

from shared.config import settings
from shared.integrations.feishu.bitable import BitableService
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

logger = get_logger("analysis_agent.milestone")


class MilestoneChecker:
    def __init__(self, bitable: BitableService):
        self._bitable = bitable

    async def check(self) -> list[dict]:
        """检查里程碑关联的子任务风险，返回风险列表"""
        tasks = await self._fetch_tasks()
        risks = []

        # 按 Feature ID 分组
        by_feature: dict[str, list[dict]] = {}
        for t in tasks:
            fid = t.get("关联 Feature ID (关键字段)", "")
            if fid:
                fid_str = str(fid).strip().lstrip("#")
                by_feature.setdefault(fid_str, []).append(t)

        for fid, subtasks in by_feature.items():
            blocked = [t for t in subtasks if "阻塞" in t.get("状态", "") or "Blocked" in t.get("状态", "")]
            total = len(subtasks)
            completed = sum(1 for t in subtasks if "完成" in t.get("状态", ""))

            if blocked:
                risks.append({
                    "feature_id": fid,
                    "type": "blocked_subtasks",
                    "severity": "critical" if len(blocked) > 1 else "warning",
                    "message": f"Feature #{fid}: {len(blocked)}/{total} 子任务阻塞",
                    "blocked_tasks": [t.get("任务(动宾短语)", "") for t in blocked],
                })

            if total > 0 and completed / total < 0.3:
                # 进度不足 30% 的 feature
                risks.append({
                    "feature_id": fid,
                    "type": "low_progress",
                    "severity": "warning",
                    "message": f"Feature #{fid}: 完成率 {completed}/{total} ({int(completed/total*100)}%)",
                })

        return risks

    async def push_risks(self, risks: list[dict]) -> bool:
        if not risks or not settings.feishu_report_chat_id:
            return False
        try:
            lines = ["🚩 里程碑风险预警\n"]
            for r in risks:
                icon = "🔴" if r["severity"] == "critical" else "🟡"
                lines.append(f"{icon} {r['message']}")
                if r.get("blocked_tasks"):
                    for bt in r["blocked_tasks"]:
                        lines.append(f"    ↳ {bt}")

            client = get_feishu_client()
            content = json.dumps({"text": "\n".join(lines)}, ensure_ascii=False)
            await client.send_message(
                receive_id=settings.feishu_report_chat_id,
                receive_id_type="chat_id", msg_type="text", content=content,
            )
            logger.info("milestone_risks_pushed", count=len(risks))
            return True
        except Exception as e:
            logger.error("milestone_push_failed", error=str(e))
            return False

    async def _fetch_tasks(self) -> list[dict]:
        app_token = settings.feishu_pm_app_token
        table_id = settings.feishu_pm_task_table_id
        if not app_token or not table_id:
            logger.warning("fetch_tasks_missing_config", has_app_token=bool(app_token), has_table_id=bool(table_id))
            return []
        records = await self._bitable.list_all_records(app_token=app_token, table_id=table_id)
        return [r.get("fields", {}) for r in records]
