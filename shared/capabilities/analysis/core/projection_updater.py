"""Projection-update consumer for the Analysis projection (DDD-004 follow-up).

Refreshes the `analysis_work_package_projection` and
`analysis_subtask_progress_projection` tables from the upstream
source domains (OpenProject, Feishu Bitable) so Analysis use cases
can stop reading those domains directly. Per `data-ownership.md`
§1.8 the projection is append/replace; this updater is the write
side that consumers (e.g. `sync.completed` event handlers) call.

The updater is intentionally pure: it depends on the typed source
ports (`OpenProjectWorkPackagePort`, `BitableTablePort`) and the
typed projection write port (`WorkPackageProjectionWriter`). It
performs the field-by-field translation from source-domain shapes
to projection value objects and upserts row-at-a-time so failures
are partial-progress rather than all-or-nothing.

Wiring to the `sync.completed` event handler is the next DDD-004
follow-up PR; the updater itself ships first so it can be unit
tested in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from shared.core import BitableTablePort, OpenProjectWorkPackagePort
from shared.utils.logger import get_logger

from .domain.projection import (
    SubtaskProgressProjection,
    WorkPackageProjection,
)

logger = get_logger("analysis_module.projection_updater")


class WorkPackageProjectionWriter(Protocol):
    """Write-side port for projection upserts.

    Mirrors the in-memory and SQLAlchemy adapters; the read-side
    `WorkPackageProjectionPort` lives in `core/domain/projection.py`.
    """

    async def upsert_work_package(
        self, projection: WorkPackageProjection
    ) -> None:
        """Store the latest snapshot for one work package."""

    async def upsert_subtask(
        self, projection: SubtaskProgressProjection
    ) -> None:
        """Store the latest snapshot for one subtask record."""


def _parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _project_work_package(wp: dict[str, Any]) -> WorkPackageProjection:
    """Translate one OpenProject work package dict into a projection."""
    links = wp.get("_links", {}) or {}
    project_href = (links.get("project") or {}).get("href") or ""
    project_id: int | None = None
    if project_href:
        try:
            project_id = int(project_href.split("/")[-1])
        except (ValueError, IndexError):
            project_id = None

    parent_href = (links.get("parent") or {}).get("href") or ""
    parent_id: int | None = None
    if parent_href:
        try:
            parent_id = int(parent_href.split("/")[-1])
        except (ValueError, IndexError):
            parent_id = None

    type_name = (links.get("type") or {}).get("title")
    status_name = (links.get("status") or {}).get("title") or "unknown"
    assigned_to = (links.get("assignedTo") or {}).get("title")

    return WorkPackageProjection(
        wp_id=int(wp.get("id") or 0),
        project_id=project_id,
        subject=str(wp.get("subject") or ""),
        type_name=type_name,
        status_name=status_name,
        percentage_done=int(wp.get("percentageDone") or 0),
        assigned_to=assigned_to,
        parent_id=parent_id,
        due_date=_parse_optional_datetime(wp.get("dueDate")),
        updated_at=_parse_optional_datetime(wp.get("updatedAt")) or datetime.now(UTC),
        extra={},
    )


def _project_subtask(record: dict[str, Any]) -> SubtaskProgressProjection | None:
    """Translate one Feishu Bitable subtask record into a projection."""
    record_id = record.get("record_id") or record.get("id")
    if not record_id:
        return None
    fields = record.get("fields", {}) or {}

    parent_wp_id = _parse_optional_int(fields.get("parent_op_id"))
    if parent_wp_id is None:
        return None

    status = str(fields.get("subtask_status") or "unknown")
    completed = "完成" in status or status.lower() in {"done", "completed", "closed"}

    return SubtaskProgressProjection(
        parent_wp_id=parent_wp_id,
        subtask_record_id=str(record_id),
        subtask_status=status,
        completed=completed,
        updated_at=datetime.now(UTC),
    )


class ProjectionUpdater:
    """Refresh the Analysis projection from upstream source domains."""

    def __init__(
        self,
        *,
        op_client: OpenProjectWorkPackagePort,
        bitable: BitableTablePort,
        writer: WorkPackageProjectionWriter,
        bitable_app_token: str | None = None,
        bitable_table_id: str | None = None,
    ) -> None:
        self._op = op_client
        self._bitable = bitable
        self._writer = writer
        self._app_token = bitable_app_token
        self._table_id = bitable_table_id

    async def refresh_work_packages(
        self, *, project_id: int | None = None
    ) -> int:
        """Pull work packages from OpenProject and upsert the projection."""
        try:
            work_packages = await self._op.get_work_packages(project_id=project_id)
        except Exception as exc:
            logger.error("projection_refresh_op_fetch_failed", error=str(exc))
            return 0

        upserted = 0
        for wp in work_packages:
            try:
                await self._writer.upsert_work_package(_project_work_package(wp))
                upserted += 1
            except Exception as exc:
                logger.warning(
                    "projection_upsert_wp_failed",
                    wp_id=wp.get("id"),
                    error=str(exc),
                )
        logger.info("projection_refresh_work_packages_done", count=upserted)
        return upserted

    async def refresh_subtasks(self) -> int:
        """Pull subtasks from Feishu Bitable and upsert the projection."""
        try:
            records = await self._bitable.list_all_records(
                app_token=self._app_token,
                table_id=self._table_id,
            )
        except Exception as exc:
            logger.error("projection_refresh_bitable_fetch_failed", error=str(exc))
            return 0

        upserted = 0
        for record in records:
            projection = _project_subtask(record)
            if projection is None:
                continue
            try:
                await self._writer.upsert_subtask(projection)
                upserted += 1
            except Exception as exc:
                logger.warning(
                    "projection_upsert_subtask_failed",
                    record_id=record.get("record_id"),
                    error=str(exc),
                )
        logger.info("projection_refresh_subtasks_done", count=upserted)
        return upserted

    async def refresh_all(
        self, *, project_id: int | None = None
    ) -> dict[str, int]:
        """Run both work-package and subtask refresh passes."""
        wp_count = await self.refresh_work_packages(project_id=project_id)
        subtask_count = await self.refresh_subtasks()
        return {"work_packages": wp_count, "subtasks": subtask_count}
