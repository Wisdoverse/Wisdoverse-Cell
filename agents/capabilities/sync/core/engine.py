"""
Sync Engine - OpenProject ↔ 飞书双向同步引擎

从 feishu-to-openproject/src/sync/engine.py 迁移，
适配 project_cell 的依赖注入和事件驱动架构。
"""
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from shared.infra.event_bus import EventBus
from shared.integrations.feishu.bitable import BitableService
from shared.integrations.openproject.client import OpenProjectClient
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..db.database import DatabaseManager
from ..db.repository import (
    SubtaskMappingRepository,
    SyncLockRepository,
    SyncLogRepository,
    SyncMappingRepository,
)
from .mapper import data_mapper
from .progress import calculate_progress_from_subtasks

logger = get_logger("sync_agent.engine")


class SyncEngine:
    """OpenProject ↔ 飞书双向同步引擎"""

    def __init__(
        self,
        db_manager: DatabaseManager,
        op_client: OpenProjectClient,
        bitable: BitableService,
        event_bus: EventBus | None = None,
        decompose_filter: Callable[[int], bool] | None = None,
    ):
        self._db = db_manager
        self._op = op_client
        self._bitable = bitable
        self._event_bus = event_bus
        self._decompose_filter = decompose_filter

    @asynccontextmanager
    async def _acquire_lock(self, lock_name: str) -> AsyncIterator[bool]:
        """Acquire distributed lock, yield bool, release on exit."""
        acquired = False
        try:
            async with self._db.session() as session:
                lock_repo = SyncLockRepository(session)
                acquired = await lock_repo.acquire(lock_name, "sync-agent")
                if not acquired:
                    logger.warning("sync_lock_held", lock=lock_name)
                yield acquired
        finally:
            if acquired:
                try:
                    async with self._db.session() as release_session:
                        release_repo = SyncLockRepository(release_session)
                        await release_repo.release(lock_name)
                except Exception as release_err:
                    logger.error(
                        "sync_lock_release_failed",
                        lock=lock_name,
                        error=str(release_err),
                        error_type=type(release_err).__name__,
                    )

    async def _load_member_map(self) -> dict[str, str]:
        member_map: dict[str, str] = {}
        try:
            from shared.config import settings as _settings
            if _settings.feishu_pm_app_token and _settings.feishu_pm_member_table_id:
                member_records = await self._bitable.list_all_records(
                    app_token=_settings.feishu_pm_app_token,
                    table_id=_settings.feishu_pm_member_table_id,
                )
                member_map = data_mapper.build_member_map(member_records)
                logger.info("member_map_loaded", count=len(member_map))
        except Exception as e:
            logger.warning("member_map_load_failed", error=str(e))
        return member_map

    async def _sync_single_work_package(
        self,
        wp: dict,
        wp_data: Any,
        mapping_repo: SyncMappingRepository,
        member_map: dict[str, str],
        parent_ids: set[int],
    ) -> None:
        mapping = await mapping_repo.get_by_op_id(wp_data.op_id)
        fields = data_mapper.work_package_to_feishu_fields(wp_data, member_map)

        if mapping and mapping.feishu_record_id:
            await self._bitable.update_record(mapping.feishu_record_id, fields)
        else:
            record_id = await self._bitable.create_record(fields)
            await mapping_repo.upsert(
                op_id=wp_data.op_id,
                record_id=record_id,
                project_id=wp_data.project_id,
                title=wp_data.title,
            )

        await self._maybe_publish_decompose(wp, wp_data, parent_ids)

    async def sync_op_to_feishu(self, project_id: int | None = None) -> dict[str, Any]:
        """OP → 飞書：同步工作包到多维表格"""
        async with self._acquire_lock("sync_op_to_feishu") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "lock_held"}
            return await self._do_sync_op_to_feishu(project_id)

    async def _do_sync_op_to_feishu(self, project_id: int | None) -> dict[str, Any]:
        async with self._db.session() as session:
            log_repo = SyncLogRepository(session)
            mapping_repo = SyncMappingRepository(session)

            log = await log_repo.create("op_to_feishu", "started")
            processed = 0
            errors = []

            try:
                member_map = await self._load_member_map()

                work_packages = await self._op.get_work_packages(project_id=project_id)
                logger.info("sync_wp_found", count=len(work_packages))

                parent_ids: set[int] = set()
                for wp in work_packages:
                    parent_href = wp.get("_links", {}).get("parent", {}).get("href")
                    if parent_href:
                        try:
                            parent_ids.add(int(parent_href.split("/")[-1]))
                        except (ValueError, IndexError):
                            pass

                for wp in work_packages:
                    try:
                        wp_data = data_mapper.op_to_work_package_data(wp)
                        await self._sync_single_work_package(
                            wp, wp_data, mapping_repo, member_map, parent_ids,
                        )
                        processed += 1
                    except Exception as e:
                        logger.error("sync_wp_error", wp_id=wp.get("id"), error=str(e))
                        errors.append(str(e))

                await log_repo.complete(log.id, processed)
                return {"status": "success", "processed": processed, "errors": errors}

            except Exception as e:
                logger.error("sync_op_to_feishu_failed", error=str(e))
                await log_repo.complete(log.id, processed, str(e))
                return {"status": "failed", "processed": processed, "error": str(e)}

    async def _maybe_publish_decompose(self, wp: dict, wp_data: Any, parent_ids: set[int]) -> None:
        """Publish a decompose event if the work package needs decomposition or refinement."""
        if not self._event_bus or not self._decompose_filter:
            return

        wp_type = wp.get("_links", {}).get("type", {}).get("title", "")

        needs_decompose = wp_type in ("Feature", "Epic") and not wp_data.parent_id
        needs_refinement = wp_type == "Task" and wp_data.op_id not in parent_ids

        if not (needs_decompose or needs_refinement):
            return
        if not self._decompose_filter(wp_data.project_id):
            return

        project_name = wp.get("_links", {}).get("project", {}).get("title", "")
        assignee_href = wp.get("_links", {}).get("assignee", {}).get("href", "")
        assignee_id = int(assignee_href.split("/")[-1]) if assignee_href else None

        decompose_event = Event.create(
            event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            source_agent="sync-agent",
            payload={
                "wp_id": wp_data.op_id,
                "subject": wp_data.title,
                "description": wp_data.description or "",
                "wp_type": wp_type if needs_decompose else "Task",
                "project_id": wp_data.project_id,
                "project_name": project_name,
                "assignee": wp_data.assignee or "",
                "assignee_id": assignee_id,
            },
        )
        await self._event_bus.publish(decompose_event)
        log_event = "decompose_event_published" if needs_decompose else "task_check_event_published"
        logger.info(log_event, wp_id=wp_data.op_id, wp_type=wp_type)

    async def _update_parent_progress(self, parent_op_id: int, subtasks: list[dict]) -> None:
        progress = calculate_progress_from_subtasks(subtasks)
        await self._op.update_work_package(parent_op_id, {"percentageDone": progress})
        logger.info("sync_progress_updated", wp_id=parent_op_id, progress=progress)

    async def sync_feishu_to_op(self) -> dict[str, Any]:
        """飞书 → OP：根据子任务完成状态更新进度"""
        async with self._acquire_lock("sync_feishu_to_op") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "lock_held"}
            return await self._do_sync_feishu_to_op()

    async def _do_sync_feishu_to_op(self) -> dict[str, Any]:
        async with self._db.session() as session:
            log_repo = SyncLogRepository(session)
            subtask_repo = SubtaskMappingRepository(session)

            log = await log_repo.create("feishu_to_op", "started")
            processed = 0
            errors = []

            try:
                all_records = await self._bitable.list_all_records()
                logger.info("sync_feishu_records_found", count=len(all_records))

                subtasks_by_parent: dict[int, list[dict]] = {}
                for record in all_records:
                    record_data = data_mapper.feishu_to_record_data(record)
                    if record_data.parent_op_id:
                        subtasks_by_parent.setdefault(record_data.parent_op_id, []).append({
                            "subtask_status": record_data.subtask_status,
                            "subtask_name": record_data.subtask_name,
                        })
                        await subtask_repo.upsert(
                            parent_op_id=record_data.parent_op_id,
                            record_id=record_data.record_id,
                            name=record_data.subtask_name,
                            status=record_data.subtask_status,
                        )

                for parent_op_id, subtasks in subtasks_by_parent.items():
                    try:
                        await self._update_parent_progress(parent_op_id, subtasks)
                        processed += 1
                    except Exception as e:
                        logger.error("sync_progress_error", wp_id=parent_op_id, error=str(e))
                        errors.append(str(e))

                await log_repo.complete(log.id, processed)
                return {"status": "success", "processed": processed, "errors": errors}

            except Exception as e:
                logger.error("sync_feishu_to_op_failed", error=str(e))
                await log_repo.complete(log.id, processed, str(e))
                return {"status": "failed", "processed": processed, "error": str(e)}

    async def full_sync(self, project_id: int | None = None) -> dict[str, Any]:
        """全量双向同步"""
        op_result = await self.sync_op_to_feishu(project_id)
        feishu_result = await self.sync_feishu_to_op()

        total = op_result.get("processed", 0) + feishu_result.get("processed", 0)

        op_status = op_result.get("status", "unknown")
        feishu_status = feishu_result.get("status", "unknown")
        if op_status == "failed" or feishu_status == "failed":
            status = (
                "partial_failure"
                if (op_status == "success" or feishu_status == "success")
                else "failed"
            )
        elif op_status == "skipped" and feishu_status == "skipped":
            status = "skipped"
        else:
            status = "success"

        return {
            "status": status,
            "total_processed": total,
            "op_to_feishu": op_result,
            "feishu_to_op": feishu_result,
        }
