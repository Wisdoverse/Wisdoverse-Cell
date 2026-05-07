"""OpenProject work-package synchronization boundary."""

from typing import Any, Callable

from shared.core import BitableTablePort, OpenProjectWorkPackagePort
from shared.infra.event_bus import EventBus
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..db.database import DatabaseManager
from ..db.repository import SyncLogRepository, SyncMappingRepository
from .locking import acquire_sync_lock
from .mapper import data_mapper

logger = get_logger("sync_capability.openproject")


class OpenProjectSyncEngine:
    """Synchronize OpenProject work packages into downstream projections."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
        event_bus: EventBus | None = None,
        decompose_filter: Callable[[int], bool] | None = None,
        member_table_app_token: str | None = None,
        member_table_id: str | None = None,
    ):
        self._db = db_manager
        self._op = op_client
        self._bitable = bitable
        self._event_bus = event_bus
        self._decompose_filter = decompose_filter
        self._member_table_app_token = member_table_app_token
        self._member_table_id = member_table_id

    async def _load_member_map(self) -> dict[str, str]:
        member_map: dict[str, str] = {}
        if not self._member_table_app_token or not self._member_table_id:
            return member_map
        try:
            member_records = await self._bitable.list_all_records(
                app_token=self._member_table_app_token,
                table_id=self._member_table_id,
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
        trace_id: str | None,
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

        await self._maybe_publish_decompose(wp, wp_data, parent_ids, trace_id)

    async def sync_to_bitable(
        self,
        project_id: int | None = None,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Mirror OpenProject work packages to the Feishu Bitable projection."""
        async with acquire_sync_lock(self._db, "sync_op_to_feishu") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "lock_held"}
            return await self._do_sync_to_bitable(project_id, trace_id)

    async def _do_sync_to_bitable(
        self,
        project_id: int | None,
        trace_id: str | None,
    ) -> dict[str, Any]:
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
                            wp,
                            wp_data,
                            mapping_repo,
                            member_map,
                            parent_ids,
                            trace_id,
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

    async def _maybe_publish_decompose(
        self,
        wp: dict,
        wp_data: Any,
        parent_ids: set[int],
        trace_id: str | None,
    ) -> None:
        """Publish a decompose event if a work package needs refinement."""
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
            source_agent="sync-module",
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
            trace_id=trace_id,
        )
        await self._event_bus.publish(decompose_event)
        log_event = (
            "decompose_event_published"
            if needs_decompose
            else "task_check_event_published"
        )
        logger.info(log_event, wp_id=wp_data.op_id, wp_type=wp_type)
