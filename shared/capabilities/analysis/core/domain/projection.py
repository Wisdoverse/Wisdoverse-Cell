"""Analysis projection seed (DDD-004).

Seeds the Published-Language read-model that Analysis use cases will
consume in place of direct source-domain reads
(`OpenProjectWorkPackagePort.get_work_packages`,
`BitableTablePort.list_all_records`) per ``data-ownership.md`` rule 4
("Analysis reads only projections"), the §2.9 broken Customer/Supplier
finding in ``module-boundaries.md``, and audit row DDD-004.

This module ships the **port shape only** (DTOs + Protocol). The
projection table SQLAlchemy mapping, the Alembic migration, the
projection-update event consumer, and the use-case migration all
follow in dedicated PRs per ``architecture-principles.md`` §3 ("no
mass file moves").

The DTO is intentionally narrow — only the fields Analysis actually
reads today. New fields land per consumer need; the projection is a
view over the upstream domain, not a redefinition.

Projection contract (rule from `data-ownership.md` §1.8):

- The projection is **append/replace**, never a source of truth.
- Refreshed by an event consumer or scheduled job that watches the
  source-domain events (`pjm.decomposition-*`, `sync.completed`,
  `qa.acceptance-completed`, etc.) and writes the projected rows.
- Analysis must depend only on `WorkPackageProjectionPort`; the
  existing `OpenProjectWorkPackagePort` and `BitableTablePort`
  imports in `daily_report.py` and `weekly_report.py` are migrated
  to read through this port instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class WorkPackageProjection:
    """Projected snapshot of one OpenProject work package.

    Analysis reads these. The projection is owned by the Analysis
    capability and refreshed from upstream events; the source domain
    (Sync / PJM / Dev) never reads it.
    """

    wp_id: int
    project_id: int | None
    subject: str
    type_name: str | None
    status_name: str
    percentage_done: int
    assigned_to: str | None
    parent_id: int | None
    due_date: datetime | None
    updated_at: datetime
    # Free-form bag for fields that vary by upstream system but are
    # not yet promoted to typed columns. Keeps the projection
    # forward-compatible without forcing a migration for every new
    # field. Promote to a typed field when a consumer needs it.
    extra: dict[str, str]


@dataclass(frozen=True, slots=True)
class SubtaskProgressProjection:
    """Projected snapshot of one Feishu Bitable subtask record.

    Analysis reads these to compute progress back-flow without
    touching the source Bitable port.
    """

    parent_wp_id: int
    subtask_record_id: str
    subtask_status: str
    completed: bool
    updated_at: datetime
    title: str = ""
    blocked_reason: str = ""
    feature_id: str | None = None


@runtime_checkable
class WorkPackageProjectionPort(Protocol):
    """Read-only projection port that replaces direct OP / Bitable reads.

    Analysis use cases consume this port. Implementations live in
    `shared/capabilities/analysis/db/` once the projection table
    migration lands. Per `data-ownership.md` §1.8 the projection is
    never written by Analysis — only consumed.
    """

    async def list_work_packages(
        self,
        *,
        project_id: int | None = None,
        updated_since: datetime | None = None,
    ) -> list[WorkPackageProjection]:
        """Return the latest projected work-package snapshots."""

    async def list_subtask_progress(
        self,
        *,
        parent_wp_id: int | None = None,
        updated_since: datetime | None = None,
    ) -> list[SubtaskProgressProjection]:
        """Return the latest projected subtask-progress snapshots."""
