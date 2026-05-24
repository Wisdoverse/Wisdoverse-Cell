"""Feishu Bitable synchronization boundary."""

from typing import Any

from shared.core import BitableTablePort, EventPublisher, OpenProjectWorkPackagePort
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..domain.sync_operation import SyncOperation, SyncOperationStatus, SyncSide
from ..domain.sync_values import ParentSubtaskRollup, SyncProjectionPolicy
from ..locking import acquire_sync_lock
from ..mapper import data_mapper
from ..sync_ports import FeishuBitableSyncStore, SyncLockStore

logger = get_logger("sync_capability.feishu_bitable")


class FeishuBitableSyncEngine:
    """Synchronize Feishu Bitable subtask state back to OpenProject progress."""

    def __init__(
        self,
        sync_store: FeishuBitableSyncStore,
        lock_store: SyncLockStore,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
        event_publisher: EventPublisher | None = None,
        projection_policy: SyncProjectionPolicy | None = None,
    ):
        self._sync_store = sync_store
        self._lock_store = lock_store
        self._op = op_client
        self._bitable = bitable
        self._event_publisher = event_publisher
        self._projection_policy = projection_policy or SyncProjectionPolicy()

    async def sync_progress_to_openproject(
        self,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Read Feishu Bitable subtasks and update OpenProject parent progress."""
        async with acquire_sync_lock(self._lock_store, "sync_feishu_to_op") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "lock_held"}
            return await self._do_sync_progress_to_openproject(trace_id=trace_id)

    async def _do_sync_progress_to_openproject(
        self,
        *,
        trace_id: str | None,
    ) -> dict[str, Any]:
        staged_events: list[Event] = []
        async with self._sync_store.transaction() as store:
            log = await store.create_log("feishu_to_op", "started")
            op = SyncOperation(operation_id=str(log.id), side=SyncSide.FEISHU_BITABLE)
            op.transition_to(SyncOperationStatus.RUNNING)
            processed = 0
            errors: list[str] = []

            try:
                all_records = await self._bitable.list_all_records()
                logger.info("sync_feishu_records_found", count=len(all_records))

                subtasks = []
                for record in all_records:
                    try:
                        record_data = data_mapper.feishu_to_record_data(record)
                        subtask = self._projection_policy.subtask_rollup_item(
                            record_data
                        )
                    except Exception as e:
                        logger.error(
                            "sync_subtask_mapping_error",
                            record_id=record.get("record_id"),
                            error=str(e),
                        )
                        errors.append(str(e))
                        continue
                    if subtask is None:
                        continue
                    subtasks.append(subtask)
                    await store.upsert_subtask(
                        parent_op_id=subtask.parent_op_id,
                        record_id=subtask.feishu_record_id,
                        name=subtask.subtask_name,
                        status=subtask.subtask_status,
                    )

                for rollup in self._projection_policy.parent_rollups(subtasks):
                    try:
                        await self._update_parent_progress(rollup)
                        progress_event = self._progress_updated_event(
                            rollup,
                            trace_id=trace_id,
                        )
                        await store.stage_event(progress_event)
                        staged_events.append(progress_event)
                        processed += 1
                    except Exception as e:
                        logger.error(
                            "sync_progress_error",
                            wp_id=rollup.parent_op_id,
                            error=str(e),
                        )
                        errors.append(str(e))

                await store.complete_log(log.id, processed)
                op.transition_to(
                    SyncOperationStatus.SUCCEEDED, processed_delta=processed
                )
                result = {"status": "success", "processed": processed, "errors": errors}

            except Exception as e:
                logger.error("sync_feishu_to_op_failed", error=str(e))
                await store.complete_log(log.id, processed, str(e))
                op.transition_to(SyncOperationStatus.FAILED)
                return {"status": "failed", "processed": processed, "error": str(e)}

        for event in staged_events:
            await self._publish_staged_sync_event(event)
        return result

    async def _update_parent_progress(
        self,
        rollup: ParentSubtaskRollup,
    ) -> None:
        progress = rollup.progress_percent
        await self._op.update_work_package(
            rollup.parent_op_id,
            {"percentageDone": progress},
        )
        logger.info(
            "sync_progress_updated",
            wp_id=rollup.parent_op_id,
            progress=progress,
        )

    def _progress_updated_event(
        self,
        rollup: ParentSubtaskRollup,
        *,
        trace_id: str | None,
    ) -> Event:
        return Event.create(
            event_type=EventTypes.SYNC_PROGRESS_UPDATED,
            source_agent="sync-module",
            payload={
                "parent_op_id": int(rollup.parent_op_id),
                "progress_percent": rollup.progress_percent,
                "subtask_count": len(rollup.subtasks),
                "completed_subtask_count": rollup.completed_subtask_count,
                "scope": "feishu_bitable",
            },
            trace_id=trace_id,
        )

    async def _publish_staged_sync_event(self, event: Event) -> None:
        """Publish a Sync event already persisted in the Feishu-side outbox."""
        if self._event_publisher is None:
            return
        try:
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("sync_event_publish_rejected")
            await self._mark_sync_event_published(event)
        except Exception as exc:
            await self._mark_sync_event_failed(event, exc)
            logger.error(
                "sync_event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_sync_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published outbox event."""
        try:
            await self._sync_store.mark_event_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "sync_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_sync_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an outbox event publish attempt."""
        try:
            await self._sync_store.mark_event_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "sync_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )
