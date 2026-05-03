"""Compatibility orchestrator for split sync capability engines."""

from typing import Any, Callable

from shared.core import BitableTablePort, OpenProjectWorkPackagePort
from shared.infra.event_bus import EventBus

from ..db.database import DatabaseManager
from .feishu_bitable_sync import FeishuBitableSyncEngine
from .openproject_sync import OpenProjectSyncEngine


class SyncEngine:
    """Orchestrate OpenProject and Feishu Bitable sync boundaries.

    This class preserves the previous sync-agent API while delegating platform
    work to two bounded engines:
    - OpenProjectSyncEngine: OpenProject work packages -> Bitable projection.
    - FeishuBitableSyncEngine: Bitable subtask status -> OpenProject progress.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
        event_bus: EventBus | None = None,
        decompose_filter: Callable[[int], bool] | None = None,
    ):
        self._db = db_manager
        self._op = op_client
        self._bitable = bitable
        self.openproject = OpenProjectSyncEngine(
            db_manager=db_manager,
            op_client=op_client,
            bitable=bitable,
            event_bus=event_bus,
            decompose_filter=decompose_filter,
        )
        self.feishu_bitable = FeishuBitableSyncEngine(
            db_manager=db_manager,
            op_client=op_client,
            bitable=bitable,
        )

    async def sync_op_to_feishu(self, project_id: int | None = None) -> dict[str, Any]:
        """Backward-compatible OpenProject-to-Bitable sync entrypoint."""
        return await self.openproject.sync_to_bitable(project_id=project_id)

    async def sync_feishu_to_op(self) -> dict[str, Any]:
        """Backward-compatible Bitable-to-OpenProject sync entrypoint."""
        return await self.feishu_bitable.sync_progress_to_openproject()

    async def full_sync(self, project_id: int | None = None) -> dict[str, Any]:
        """Run both split sync boundaries and summarize the combined result."""
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
