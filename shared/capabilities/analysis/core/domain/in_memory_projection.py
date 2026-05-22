"""In-memory adapter for the Analysis projection port (DDD-004 impl step).

Implementation follow-up to the DDD-004 seed (port + value objects).
Ships a runtime adapter that satisfies ``WorkPackageProjectionPort``
backed by in-memory state, suitable for unit-test injection and for
the dev / local-compose path before the real Alembic projection
table lands.

The production-grade SQLAlchemy-backed adapter lives in
``shared/capabilities/analysis/db/`` once the migration follow-up
PR adds the projection tables. Until then, daily_report and
weekly_report consume this in-memory adapter through DI at the
``service/agent.py`` boundary.

Per ``data-ownership.md`` §1.8 ("Projections are append/replace; never
write owners"), this in-memory adapter is intentionally simple: it
exposes an ``upsert`` write side for the projection consumer to call
when source-domain events arrive, and read methods that satisfy the
port contract. Production semantics (replay safety, idempotency) move
into the SQLAlchemy adapter when it lands.
"""

from __future__ import annotations

from datetime import datetime

from .projection import (
    SubtaskProgressProjection,
    WorkPackageProjection,
    WorkPackageProjectionPort,
)


class InMemoryWorkPackageProjectionStore(WorkPackageProjectionPort):
    """In-memory `WorkPackageProjectionPort` for tests + dev.

    Stores the latest projected snapshot per `wp_id` and per
    `subtask_record_id`. Newer upserts replace older snapshots
    (append/replace semantics; never a write owner).
    """

    def __init__(self) -> None:
        self._work_packages: dict[int, WorkPackageProjection] = {}
        self._subtasks: dict[str, SubtaskProgressProjection] = {}

    # ── Write side (called by the projection consumer) ────────────────

    def upsert_work_package(self, projection: WorkPackageProjection) -> None:
        """Store the latest snapshot for one work package."""
        self._work_packages[projection.wp_id] = projection

    def upsert_subtask(self, projection: SubtaskProgressProjection) -> None:
        """Store the latest snapshot for one subtask record."""
        self._subtasks[projection.subtask_record_id] = projection

    # ── Read side (satisfies WorkPackageProjectionPort) ──────────────

    async def list_work_packages(
        self,
        *,
        project_id: int | None = None,
        updated_since: datetime | None = None,
    ) -> list[WorkPackageProjection]:
        rows = list(self._work_packages.values())
        if project_id is not None:
            rows = [r for r in rows if r.project_id == project_id]
        if updated_since is not None:
            rows = [r for r in rows if r.updated_at >= updated_since]
        return rows

    async def list_subtask_progress(
        self,
        *,
        parent_wp_id: int | None = None,
        updated_since: datetime | None = None,
    ) -> list[SubtaskProgressProjection]:
        rows = list(self._subtasks.values())
        if parent_wp_id is not None:
            rows = [r for r in rows if r.parent_wp_id == parent_wp_id]
        if updated_since is not None:
            rows = [r for r in rows if r.updated_at >= updated_since]
        return rows
