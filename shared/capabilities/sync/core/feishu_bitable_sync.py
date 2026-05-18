"""Feishu Bitable synchronization boundary."""

from typing import Any

from shared.core import BitableTablePort, OpenProjectWorkPackagePort
from shared.utils.logger import get_logger

from .locking import acquire_sync_lock
from .mapper import data_mapper
from .progress import calculate_progress_from_subtasks
from .sync_ports import FeishuBitableSyncStore, SyncLockStore

logger = get_logger("sync_capability.feishu_bitable")


class FeishuBitableSyncEngine:
    """Synchronize Feishu Bitable subtask state back to OpenProject progress."""

    def __init__(
        self,
        sync_store: FeishuBitableSyncStore,
        lock_store: SyncLockStore,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
    ):
        self._sync_store = sync_store
        self._lock_store = lock_store
        self._op = op_client
        self._bitable = bitable

    async def sync_progress_to_openproject(self) -> dict[str, Any]:
        """Read Feishu Bitable subtasks and update OpenProject parent progress."""
        async with acquire_sync_lock(self._lock_store, "sync_feishu_to_op") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "lock_held"}
            return await self._do_sync_progress_to_openproject()

    async def _do_sync_progress_to_openproject(self) -> dict[str, Any]:
        async with self._sync_store.transaction() as store:
            log = await store.create_log("feishu_to_op", "started")
            processed = 0
            errors = []

            try:
                all_records = await self._bitable.list_all_records()
                logger.info("sync_feishu_records_found", count=len(all_records))

                subtasks_by_parent: dict[int, list[dict]] = {}
                for record in all_records:
                    record_data = data_mapper.feishu_to_record_data(record)
                    if record_data.parent_op_id:
                        subtasks_by_parent.setdefault(
                            record_data.parent_op_id, []
                        ).append(
                            {
                                "subtask_status": record_data.subtask_status,
                                "subtask_name": record_data.subtask_name,
                            }
                        )
                        await store.upsert_subtask(
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
                        logger.error(
                            "sync_progress_error",
                            wp_id=parent_op_id,
                            error=str(e),
                        )
                        errors.append(str(e))

                await store.complete_log(log.id, processed)
                return {"status": "success", "processed": processed, "errors": errors}

            except Exception as e:
                logger.error("sync_feishu_to_op_failed", error=str(e))
                await store.complete_log(log.id, processed, str(e))
                return {"status": "failed", "processed": processed, "error": str(e)}

    async def _update_parent_progress(
        self,
        parent_op_id: int,
        subtasks: list[dict],
    ) -> None:
        progress = calculate_progress_from_subtasks(subtasks)
        await self._op.update_work_package(parent_op_id, {"percentageDone": progress})
        logger.info("sync_progress_updated", wp_id=parent_op_id, progress=progress)
