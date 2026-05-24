"""SQLAlchemy adapter for the Analysis projection port (DDD-004 follow-up).

Production-grade `WorkPackageProjectionPort` implementation backed by
the Postgres projection tables defined in
``shared/capabilities/analysis/models/projection.py``. Mirrors the
in-memory adapter contract: an `upsert_*` write side for the
projection-update event consumer to call, and async read methods
that satisfy the port.

Per ``data-ownership.md`` §1.8 the projection is append/replace —
the write side uses an idempotent upsert keyed on the projection's
primary key so replays don't double-insert.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.domain.projection import (
    SubtaskProgressProjection,
    WorkPackageProjection,
    WorkPackageProjectionPort,
)
from ..models.projection import (
    AnalysisSubtaskProgressProjection,
    AnalysisWorkPackageProjection,
)
from .database import DatabaseManager


def _row_to_work_package(row: AnalysisWorkPackageProjection) -> WorkPackageProjection:
    return WorkPackageProjection(
        wp_id=row.wp_id,
        project_id=row.project_id,
        subject=row.subject,
        type_name=row.type_name,
        status_name=row.status_name,
        percentage_done=row.percentage_done,
        assigned_to=row.assigned_to,
        parent_id=row.parent_id,
        due_date=row.due_date,
        updated_at=row.updated_at,
        extra=dict(row.extra or {}),
    )


def _row_to_subtask(
    row: AnalysisSubtaskProgressProjection,
) -> SubtaskProgressProjection:
    return SubtaskProgressProjection(
        parent_wp_id=row.parent_wp_id,
        subtask_record_id=row.subtask_record_id,
        subtask_status=row.subtask_status,
        completed=row.completed,
        updated_at=row.updated_at,
        title=row.title,
        blocked_reason=row.blocked_reason,
        feature_id=row.feature_id,
    )


class SqlAlchemyWorkPackageProjectionStore(WorkPackageProjectionPort):
    """Postgres-backed `WorkPackageProjectionPort` adapter."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def upsert_work_package(
        self, projection: WorkPackageProjection
    ) -> None:
        async with self._db_manager.session() as session:
            stmt = pg_insert(AnalysisWorkPackageProjection).values(
                wp_id=projection.wp_id,
                project_id=projection.project_id,
                subject=projection.subject,
                type_name=projection.type_name,
                status_name=projection.status_name,
                percentage_done=projection.percentage_done,
                assigned_to=projection.assigned_to,
                parent_id=projection.parent_id,
                due_date=projection.due_date,
                updated_at=projection.updated_at,
                extra=dict(projection.extra),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[AnalysisWorkPackageProjection.wp_id],
                set_={
                    "project_id": stmt.excluded.project_id,
                    "subject": stmt.excluded.subject,
                    "type_name": stmt.excluded.type_name,
                    "status_name": stmt.excluded.status_name,
                    "percentage_done": stmt.excluded.percentage_done,
                    "assigned_to": stmt.excluded.assigned_to,
                    "parent_id": stmt.excluded.parent_id,
                    "due_date": stmt.excluded.due_date,
                    "updated_at": stmt.excluded.updated_at,
                    "extra": stmt.excluded.extra,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def upsert_subtask(
        self, projection: SubtaskProgressProjection
    ) -> None:
        async with self._db_manager.session() as session:
            stmt = pg_insert(AnalysisSubtaskProgressProjection).values(
                subtask_record_id=projection.subtask_record_id,
                parent_wp_id=projection.parent_wp_id,
                subtask_status=projection.subtask_status,
                completed=projection.completed,
                title=projection.title,
                blocked_reason=projection.blocked_reason,
                feature_id=projection.feature_id,
                updated_at=projection.updated_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    AnalysisSubtaskProgressProjection.subtask_record_id
                ],
                set_={
                    "parent_wp_id": stmt.excluded.parent_wp_id,
                    "subtask_status": stmt.excluded.subtask_status,
                    "completed": stmt.excluded.completed,
                    "title": stmt.excluded.title,
                    "blocked_reason": stmt.excluded.blocked_reason,
                    "feature_id": stmt.excluded.feature_id,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def list_work_packages(
        self,
        *,
        project_id: int | None = None,
        updated_since: datetime | None = None,
    ) -> list[WorkPackageProjection]:
        async with self._db_manager.session() as session:
            query = select(AnalysisWorkPackageProjection)
            if project_id is not None:
                query = query.where(
                    AnalysisWorkPackageProjection.project_id == project_id
                )
            if updated_since is not None:
                query = query.where(
                    AnalysisWorkPackageProjection.updated_at >= updated_since
                )
            result = await session.execute(query)
            return [_row_to_work_package(row) for row in result.scalars().all()]

    async def list_subtask_progress(
        self,
        *,
        parent_wp_id: int | None = None,
        updated_since: datetime | None = None,
    ) -> list[SubtaskProgressProjection]:
        async with self._db_manager.session() as session:
            query = select(AnalysisSubtaskProgressProjection)
            if parent_wp_id is not None:
                query = query.where(
                    AnalysisSubtaskProgressProjection.parent_wp_id == parent_wp_id
                )
            if updated_since is not None:
                query = query.where(
                    AnalysisSubtaskProgressProjection.updated_at >= updated_since
                )
            result = await session.execute(query)
            return [_row_to_subtask(row) for row in result.scalars().all()]
