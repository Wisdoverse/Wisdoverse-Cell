"""Compatibility orchestrator for split sync capability engines."""

from typing import Any, Callable

from shared.core import (
    BitableTablePort,
    EventPublisher,
    OpenProjectWorkPackagePort,
)

from .domain.sync_operation import SyncOperationStatus, combine_side_statuses
from .feishu_bitable import FeishuBitableSyncEngine
from .openproject import OpenProjectSyncEngine
from .sync_ports import FeishuBitableSyncStore, OpenProjectSyncStore, SyncLockStore

# Mapping from the legacy result-dict status strings produced by the
# split engines to the typed SyncOperationStatus enum. Drives the
# DDD-003 implementation step that retires the H4 / P1-2 string-status
# anti-pattern in this orchestrator.
_STATUS_TO_ENUM: dict[str, SyncOperationStatus] = {
    "success": SyncOperationStatus.SUCCEEDED,
    "succeeded": SyncOperationStatus.SUCCEEDED,
    "failed": SyncOperationStatus.FAILED,
    "partial_failure": SyncOperationStatus.PARTIAL_FAILURE,
    "skipped": SyncOperationStatus.SKIPPED,
    "running": SyncOperationStatus.RUNNING,
    "pending": SyncOperationStatus.PENDING,
}

_ENUM_TO_STATUS: dict[SyncOperationStatus, str] = {
    SyncOperationStatus.SUCCEEDED: "success",
    SyncOperationStatus.FAILED: "failed",
    SyncOperationStatus.PARTIAL_FAILURE: "partial_failure",
    SyncOperationStatus.SKIPPED: "skipped",
    SyncOperationStatus.RUNNING: "running",
    SyncOperationStatus.PENDING: "pending",
}


def _coerce_status(raw: str) -> SyncOperationStatus:
    """Map a sub-engine's legacy string status into the typed enum.

    Unknown values default to PARTIAL_FAILURE so the typed combiner
    treats them conservatively (rather than promoting them to SUCCEEDED).
    """
    return _STATUS_TO_ENUM.get(raw, SyncOperationStatus.PARTIAL_FAILURE)


class SyncEngine:
    """Orchestrate OpenProject and Feishu Bitable sync boundaries.

    This class preserves the previous sync-module API while delegating platform
    work to two bounded engines:
    - OpenProjectSyncEngine: OpenProject work packages -> Bitable projection.
    - FeishuBitableSyncEngine: Bitable subtask status -> OpenProject progress.
    """

    def __init__(
        self,
        openproject_store: OpenProjectSyncStore,
        lock_store: SyncLockStore,
        feishu_bitable_store: FeishuBitableSyncStore,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
        event_publisher: EventPublisher | None = None,
        decompose_filter: Callable[[int], bool] | None = None,
        member_table_app_token: str | None = None,
        member_table_id: str | None = None,
    ):
        self._op = op_client
        self._bitable = bitable
        self.openproject = OpenProjectSyncEngine(
            sync_store=openproject_store,
            lock_store=lock_store,
            op_client=op_client,
            bitable=bitable,
            event_publisher=event_publisher,
            decompose_filter=decompose_filter,
            member_table_app_token=member_table_app_token,
            member_table_id=member_table_id,
        )
        self.feishu_bitable = FeishuBitableSyncEngine(
            sync_store=feishu_bitable_store,
            lock_store=lock_store,
            op_client=op_client,
            bitable=bitable,
            event_publisher=event_publisher,
        )

    async def sync_op_to_feishu(
        self,
        project_id: int | None = None,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Backward-compatible OpenProject-to-Bitable sync entrypoint."""
        return await self.openproject.sync_to_bitable(
            project_id=project_id,
            trace_id=trace_id,
        )

    async def sync_feishu_to_op(
        self,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Backward-compatible Bitable-to-OpenProject sync entrypoint."""
        return await self.feishu_bitable.sync_progress_to_openproject(
            trace_id=trace_id,
        )

    async def full_sync(
        self,
        project_id: int | None = None,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Run both split sync boundaries and summarize the combined result."""
        op_result = await self.sync_op_to_feishu(project_id, trace_id=trace_id)
        feishu_result = await self.sync_feishu_to_op(trace_id=trace_id)

        total = op_result.get("processed", 0) + feishu_result.get("processed", 0)

        # Drive the terminal-status decision through the typed FSM
        # combiner (DDD-003 implementation; closes the H4 / P1-2
        # string-status anti-pattern flagged in the Phase 1 audit).
        op_status = _coerce_status(op_result.get("status", "unknown"))
        feishu_status = _coerce_status(feishu_result.get("status", "unknown"))
        combined = combine_side_statuses(op_status, feishu_status)

        # Preserve the legacy "both sides skipped → SKIPPED" edge case
        # that the combiner does not model directly.
        if (
            op_status == SyncOperationStatus.SKIPPED
            and feishu_status == SyncOperationStatus.SKIPPED
        ):
            combined = SyncOperationStatus.SKIPPED

        return {
            "status": _ENUM_TO_STATUS[combined],
            "total_processed": total,
            "op_to_feishu": op_result,
            "feishu_to_op": feishu_result,
        }
