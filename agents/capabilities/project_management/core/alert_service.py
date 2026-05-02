"""预警服务 - 检测截止日期/超载/进度/阻塞风险"""

from datetime import UTC, datetime
from typing import Any

from shared.config import settings
from shared.integrations.feishu.bitable import BitableService
from shared.utils.logger import get_logger

from .config_service import PMConfigService

logger = get_logger("pjm_agent.alert")


class AlertService:
    def __init__(self, bitable: BitableService, config: PMConfigService):
        self._bitable = bitable
        self._config = config

    async def check_all(self) -> list[dict[str, Any]]:
        """执行所有预警检查"""
        alerts: list[dict] = []
        tasks = await self._fetch_tasks()
        alerts.extend(self._check_deadlines(tasks))
        alerts.extend(self._check_blocked(tasks))
        alerts.extend(self._check_progress(tasks))
        alerts.extend(self._check_workload())
        return alerts

    async def _fetch_tasks(self) -> list[dict]:
        app_token = settings.feishu_pm_app_token
        table_id = settings.feishu_pm_task_table_id
        if not app_token or not table_id:
            logger.warning(
                "fetch_tasks_missing_config",
                has_app_token=bool(app_token),
                has_table_id=bool(table_id),
            )
            return []
        records = await self._bitable.list_all_records(app_token=app_token, table_id=table_id)
        return [r.get("fields", {}) for r in records]

    def _check_deadlines(self, tasks: list[dict]) -> list[dict]:
        alerts = []
        warn_days = int(self._config.get_rule("截止日期预警天数", "3"))
        now = datetime.now(UTC)
        for task in tasks:
            due = task.get("计划完成日期")
            status = task.get("状态", "")
            if not due or "完成" in status:
                continue
            if isinstance(due, (int, float)):
                due_dt = datetime.fromtimestamp(due / 1000, tz=UTC)
            else:
                continue
            days_left = (due_dt - now).days
            name = task.get("任务(动宾短语)", "")
            if days_left < 0:
                alerts.append(
                    {
                        "type": "deadline",
                        "severity": "critical",
                        "task": name,
                        "message": f"已逾期 {abs(days_left)} 天",
                    }
                )
            elif days_left <= warn_days:
                alerts.append(
                    {
                        "type": "deadline",
                        "severity": "warning",
                        "task": name,
                        "message": f"距截止还有 {days_left} 天",
                    }
                )
        return alerts

    def _check_blocked(self, tasks: list[dict]) -> list[dict]:
        alerts = []
        for task in tasks:
            status = task.get("状态", "")
            if "阻塞" in status or "Blocked" in status:
                reason = task.get("阻塞原因", "未说明")
                alerts.append(
                    {
                        "type": "blocked",
                        "severity": "warning",
                        "task": task.get("任务(动宾短语)", ""),
                        "message": f"阻塞原因: {reason}",
                    }
                )
        return alerts

    def _check_progress(self, tasks: list[dict]) -> list[dict]:
        alerts = []
        threshold = int(self._config.get_rule("进度落后阈值", "20"))
        now = datetime.now(UTC)
        for task in tasks:
            start = task.get("开始日期")
            due = task.get("计划完成日期")
            progress = task.get("进度")
            if not all([start, due, progress is not None]):
                continue
            if not isinstance(start, (int, float)) or not isinstance(due, (int, float)):
                continue
            start_dt = datetime.fromtimestamp(start / 1000, tz=UTC)
            due_dt = datetime.fromtimestamp(due / 1000, tz=UTC)
            total_days = (due_dt - start_dt).days
            if total_days <= 0:
                continue
            elapsed_days = (now - start_dt).days
            expected = min(100, int(elapsed_days / total_days * 100))
            actual = int(progress) if progress else 0
            if expected - actual > threshold:
                alerts.append(
                    {
                        "type": "progress",
                        "severity": "warning",
                        "task": task.get("任务(动宾短语)", ""),
                        "message": f"进度落后: 预期 {expected}%, 实际 {actual}%",
                    }
                )
        return alerts

    def _check_workload(self) -> list[dict]:
        """检查成员工作负载 (Phase 2: requires workload calculation)"""
        # Phase 2: Will calculate actual workload from member table and task estimates
        return []
