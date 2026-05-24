"""Domain record for persisted Analysis report logs."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, NewType

from .report import (
    AnalysisReportKind,
    AnalysisReportStatus,
    InvalidAnalysisReportError,
    InvalidAnalysisReportTransitionError,
)

AnalysisReportLogId = NewType("AnalysisReportLogId", int)


@dataclass(frozen=True, slots=True)
class AnalysisReportLogRecord:
    """Persistence-facing entity snapshot for one generated report log."""

    id: AnalysisReportLogId | None
    report_kind: AnalysisReportKind
    report_date: datetime
    content: str
    status: AnalysisReportStatus = AnalysisReportStatus.GENERATED
    pushed_at: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id is not None and int(self.id) <= 0:
            raise InvalidAnalysisReportError("analysis report log id must be positive")
        if self.pushed_at is not None and self.status is not AnalysisReportStatus.PUSHED:
            raise InvalidAnalysisReportError("only pushed report logs can have pushed_at")

    @classmethod
    def create(
        cls,
        *,
        report_kind: AnalysisReportKind | str,
        report_date: datetime,
        content: str = "",
    ) -> "AnalysisReportLogRecord":
        """Create a new generated report-log snapshot before persistence."""
        return cls(
            id=None,
            report_kind=AnalysisReportKind(str(report_kind)),
            report_date=report_date,
            content=content,
        )

    @classmethod
    def from_record(cls, row: Any) -> "AnalysisReportLogRecord":
        """Hydrate a report-log snapshot from a persistence row."""
        raw_id = getattr(row, "id", None)
        return cls(
            id=AnalysisReportLogId(int(raw_id)) if raw_id is not None else None,
            report_kind=AnalysisReportKind(str(row.report_type)),
            report_date=row.report_date,
            content=row.content or "",
            status=AnalysisReportStatus(str(row.status)),
            pushed_at=getattr(row, "pushed_at", None),
            created_at=getattr(row, "created_at", None),
        )

    def mark_pushed(
        self,
        *,
        pushed_at: datetime | None = None,
    ) -> "AnalysisReportLogRecord":
        """Move a generated report log to pushed."""
        if self.status is not AnalysisReportStatus.GENERATED:
            raise InvalidAnalysisReportTransitionError(
                f"cannot push report log from {self.status.value}"
            )
        return replace(
            self,
            status=AnalysisReportStatus.PUSHED,
            pushed_at=pushed_at or datetime.now(UTC),
        )

    def to_persistence_kwargs(self) -> dict[str, Any]:
        """Return row constructor values for the SQLAlchemy adapter."""
        return {
            "report_type": self.report_kind.value,
            "report_date": self.report_date,
            "content": self.content,
            "status": self.status.value,
            "pushed_at": self.pushed_at,
        }

    def to_status_update_values(self) -> dict[str, Any]:
        """Return row update values for status-only writes."""
        return {
            "status": self.status.value,
            "pushed_at": self.pushed_at,
        }


__all__ = [
    "AnalysisReportLogId",
    "AnalysisReportLogRecord",
]
