"""交付物质量评估器 - AI 读取飞书文档并评分"""
# NOTE: Phase 2 stub — _evaluate_task() requires LLMGateway integration.
# Current behavior: logs and returns None for all tasks.

from shared.config import settings
from shared.integrations.feishu.bitable import BitableService
from shared.utils.logger import get_logger

logger = get_logger("analysis_agent.quality")


class QualityEvaluator:
    def __init__(self, bitable: BitableService):
        self._bitable = bitable

    async def evaluate_all(self) -> list[dict]:
        """评估所有有交付物链接的任务"""
        tasks = await self._fetch_tasks_with_deliverables()
        results = []
        for task in tasks:
            try:
                result = await self._evaluate_task(task)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error("quality_eval_error", task=task.get("name", ""), error=str(e))
        return results

    async def _fetch_tasks_with_deliverables(self) -> list[dict]:
        app_token = settings.feishu_pm_app_token
        table_id = settings.feishu_pm_task_table_id
        if not app_token or not table_id:
            return []
        records = await self._bitable.list_all_records(app_token=app_token, table_id=table_id)
        tasks = []
        for r in records:
            fields = r.get("fields", {})
            link = fields.get("交付物/产出链接")
            quality = fields.get("交付物质量")
            # 只评估有链接但还没评分的
            if link and not quality:
                tasks.append({
                    "record_id": r.get("record_id"),
                    "name": fields.get("任务(动宾短语)", ""),
                    "link": link if isinstance(link, str) else str(link),
                    "fields": fields,
                })
        return tasks

    async def _evaluate_task(self, task: dict) -> dict | None:
        """评估单个任务的交付物质量 (Phase 2: requires LLMGateway)"""
        # Phase 2: Will use LLMGateway to read document content and evaluate quality
        logger.info("quality_eval_skip", task=task["name"], reason="Phase 2: LLM evaluation not yet implemented")
        return None

    async def write_back(self, record_id: str, quality: str, comment: str) -> bool:
        """将评估结果回写到飞书表"""
        try:
            app_token = settings.feishu_pm_app_token
            table_id = settings.feishu_pm_task_table_id
            await self._bitable.update_record(
                record_id=record_id,
                fields={"交付物质量": quality, "质量评语": comment},
                app_token=app_token,
                table_id=table_id,
            )
            logger.info("quality_written_back", record_id=record_id, quality=quality)
            return True
        except Exception as e:
            logger.error("quality_writeback_failed", record_id=record_id, error=str(e))
            return False
