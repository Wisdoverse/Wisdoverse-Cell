"""Tests for Analysis report-log domain records."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from shared.capabilities.analysis.core.domain.report import (
    AnalysisReportKind,
    AnalysisReportStatus,
    InvalidAnalysisReportError,
    InvalidAnalysisReportTransitionError,
)
from shared.capabilities.analysis.core.domain.report_log import (
    AnalysisReportLogId,
    AnalysisReportLogRecord,
)


def test_report_log_record_normalizes_persistence_values() -> None:
    row = SimpleNamespace(
        id=42,
        report_type="daily",
        report_date=datetime(2026, 5, 23, tzinfo=UTC),
        content="Daily report",
        status="generated",
        pushed_at=None,
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
    )

    record = AnalysisReportLogRecord.from_record(row)

    assert record.id == AnalysisReportLogId(42)
    assert record.report_kind is AnalysisReportKind.DAILY
    assert record.status is AnalysisReportStatus.GENERATED
    assert record.to_persistence_kwargs()["report_type"] == "daily"


def test_report_log_record_guards_push_transition() -> None:
    record = AnalysisReportLogRecord.create(
        report_kind=AnalysisReportKind.WEEKLY,
        report_date=datetime(2026, 5, 23, tzinfo=UTC),
        content="Weekly report",
    )

    pushed = record.mark_pushed(pushed_at=datetime(2026, 5, 24, tzinfo=UTC))

    assert pushed.status is AnalysisReportStatus.PUSHED
    assert pushed.pushed_at == datetime(2026, 5, 24, tzinfo=UTC)
    assert pushed.to_status_update_values() == {
        "status": "pushed",
        "pushed_at": datetime(2026, 5, 24, tzinfo=UTC),
    }

    with pytest.raises(InvalidAnalysisReportTransitionError):
        pushed.mark_pushed()


def test_report_log_record_rejects_invalid_identity_and_status_pair() -> None:
    with pytest.raises(InvalidAnalysisReportError):
        AnalysisReportLogRecord(
            id=AnalysisReportLogId(0),
            report_kind=AnalysisReportKind.DAILY,
            report_date=datetime(2026, 5, 23, tzinfo=UTC),
            content="Daily report",
        )

    with pytest.raises(InvalidAnalysisReportError):
        AnalysisReportLogRecord(
            id=AnalysisReportLogId(1),
            report_kind=AnalysisReportKind.DAILY,
            report_date=datetime(2026, 5, 23, tzinfo=UTC),
            content="Daily report",
            status=AnalysisReportStatus.GENERATED,
            pushed_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
