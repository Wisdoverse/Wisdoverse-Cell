"""Domain objects for Analysis report generation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .feishu_task import AnalysisFeishuTaskSnapshot
from .projection import WorkPackageProjection


class InvalidAnalysisReportError(ValueError):
    """Raised when an Analysis report violates domain invariants."""


class InvalidAnalysisReportTransitionError(ValueError):
    """Raised when an Analysis report status transition is invalid."""


class AnalysisReportKind(StrEnum):
    """Supported Analysis report kinds."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MILESTONE = "milestone"


class AnalysisReportStatus(StrEnum):
    """Lifecycle state for a generated Analysis report."""

    GENERATED = "generated"
    PUSHED = "pushed"
    FAILED = "failed"


_COMPLETED_OP_STATUSES = frozenset({"closed", "done", "resolved", "completed"})


@dataclass(frozen=True, slots=True)
class TaskSourceStats:
    """Task statistics for one Analysis report source."""

    total: int
    completed: int
    in_progress: int
    blocked: int = 0

    def __post_init__(self) -> None:
        for field_name in ("total", "completed", "in_progress", "blocked"):
            value = getattr(self, field_name)
            if value < 0:
                raise InvalidAnalysisReportError(f"{field_name} must be non-negative")
        if self.completed + self.in_progress + self.blocked > self.total:
            raise InvalidAnalysisReportError("task source counts cannot exceed total")

    @classmethod
    def from_feishu_tasks(
        cls,
        tasks: Sequence[AnalysisFeishuTaskSnapshot],
    ) -> "TaskSourceStats":
        """Build Feishu task stats from Analysis-owned task snapshots."""
        completed = 0
        in_progress = 0
        blocked = 0
        for task in tasks:
            if task.is_blocked:
                blocked += 1
            elif task.is_completed:
                completed += 1
            elif task.is_in_progress:
                in_progress += 1
        return cls(
            total=len(tasks),
            completed=completed,
            in_progress=in_progress,
            blocked=blocked,
        )

    @classmethod
    def from_work_packages(
        cls,
        work_packages: Sequence[WorkPackageProjection],
    ) -> "TaskSourceStats":
        """Build OpenProject stats from Analysis-owned work-package projections."""
        completed = 0
        in_progress = 0
        for work_package in work_packages:
            status = work_package.status_name.lower()
            if status in _COMPLETED_OP_STATUSES:
                completed += 1
            elif "progress" in status:
                in_progress += 1
        return cls(
            total=len(work_packages),
            completed=completed,
            in_progress=in_progress,
        )

    def to_dict(self, *, include_blocked: bool = True) -> dict[str, int]:
        """Return the legacy primitive stats payload."""
        payload = {
            "total": self.total,
            "completed": self.completed,
            "in_progress": self.in_progress,
        }
        if include_blocked:
            payload["blocked"] = self.blocked
        return payload


@dataclass(frozen=True, slots=True)
class AnalysisReportStats:
    """Combined statistics for an Analysis operating report."""

    feishu: TaskSourceStats
    op: TaskSourceStats

    @property
    def total(self) -> int:
        """Return total tasks across all report sources."""
        return self.feishu.total + self.op.total

    @classmethod
    def from_sources(
        cls,
        *,
        feishu_tasks: Sequence[AnalysisFeishuTaskSnapshot],
        op_tasks: Sequence[WorkPackageProjection],
    ) -> "AnalysisReportStats":
        """Build report stats from Analysis projection inputs."""
        return cls(
            feishu=TaskSourceStats.from_feishu_tasks(feishu_tasks),
            op=TaskSourceStats.from_work_packages(op_tasks),
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return the existing API/report payload shape."""
        return {
            "total": self.total,
            "feishu": self.feishu.to_dict(),
            "op": self.op.to_dict(include_blocked=False),
        }


@dataclass(frozen=True, slots=True)
class AnalysisReportGenerated:
    """In-memory event raised when an Analysis report is generated."""

    report_kind: AnalysisReportKind
    summary: str
    total_tasks: int
    occurred_at: datetime

    @property
    def event_name(self) -> str:
        """Return the stable class-name event identifier."""
        return type(self).__name__

    def to_payload(self) -> dict[str, Any]:
        """Return a primitive payload for future outbox adapters."""
        return {
            "report_kind": self.report_kind.value,
            "summary": self.summary,
            "total_tasks": self.total_tasks,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass
class GeneratedAnalysisReport:
    """Aggregate root for one generated Analysis report."""

    report_kind: AnalysisReportKind
    content: str
    summary: str
    stats: AnalysisReportStats | None
    status: AnalysisReportStatus = AnalysisReportStatus.GENERATED
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    pushed_at: datetime | None = None
    _events: list[AnalysisReportGenerated] = field(default_factory=list)

    @classmethod
    def generate(
        cls,
        *,
        report_kind: AnalysisReportKind,
        content: str,
        summary: str,
        stats: AnalysisReportStats | None,
        generated_at: datetime | None = None,
    ) -> "GeneratedAnalysisReport":
        """Create a generated report and raise its in-memory domain event."""
        if not content:
            raise InvalidAnalysisReportError("analysis report content must not be empty")
        if not summary:
            raise InvalidAnalysisReportError("analysis report summary must not be empty")
        report = cls(
            report_kind=report_kind,
            content=content,
            summary=summary,
            stats=stats,
            generated_at=generated_at or datetime.now(UTC),
        )
        report._events.append(
            AnalysisReportGenerated(
                report_kind=report.report_kind,
                summary=report.summary,
                total_tasks=report.stats.total if report.stats is not None else 0,
                occurred_at=report.generated_at,
            )
        )
        return report

    def mark_pushed(self, *, pushed_at: datetime | None = None) -> None:
        """Mark the report as pushed to a downstream channel."""
        if self.status != AnalysisReportStatus.GENERATED:
            raise InvalidAnalysisReportTransitionError(
                f"cannot push report from {self.status.value}"
            )
        self.status = AnalysisReportStatus.PUSHED
        self.pushed_at = pushed_at or datetime.now(UTC)

    def mark_failed(self) -> None:
        """Mark the report as failed before downstream delivery."""
        if self.status == AnalysisReportStatus.PUSHED:
            raise InvalidAnalysisReportTransitionError("pushed reports cannot fail")
        self.status = AnalysisReportStatus.FAILED

    def to_response(self, *, include_stats: bool) -> dict[str, Any]:
        """Return the existing request/event response payload shape."""
        payload: dict[str, Any] = {
            "content": self.content,
            "summary": self.summary,
        }
        if include_stats:
            payload["stats"] = self.stats.to_legacy_dict() if self.stats is not None else {}
        return payload

    def pull_events(self) -> list[AnalysisReportGenerated]:
        """Drain in-memory report domain events."""
        events = list(self._events)
        self._events.clear()
        return events


__all__ = [
    "AnalysisReportGenerated",
    "AnalysisReportKind",
    "AnalysisReportStats",
    "AnalysisReportStatus",
    "GeneratedAnalysisReport",
    "InvalidAnalysisReportError",
    "InvalidAnalysisReportTransitionError",
    "TaskSourceStats",
]
