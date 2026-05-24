"""Analysis report-log repository tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.analysis.core.domain.report import AnalysisReportStatus
from shared.capabilities.analysis.core.domain.report_log import AnalysisReportLogRecord
from shared.capabilities.analysis.db.repository import ReportLogRepository


def _result(row):
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    return result


def _row(**overrides):
    defaults = {
        "id": 7,
        "report_type": "daily",
        "report_date": datetime(2026, 5, 23, tzinfo=UTC),
        "content": "Daily report",
        "status": "generated",
        "pushed_at": None,
        "created_at": datetime(2026, 5, 23, tzinfo=UTC),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_report_log_repository_create_returns_domain_record() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    repository = ReportLogRepository(session)

    record = await repository.create(
        report_type="daily",
        report_date=datetime(2026, 5, 23, tzinfo=UTC),
        content="Daily report",
    )

    added = session.add.call_args.args[0]
    assert isinstance(record, AnalysisReportLogRecord)
    assert record.report_kind.value == "daily"
    assert record.status is AnalysisReportStatus.GENERATED
    assert added.report_type == "daily"
    assert added.status == "generated"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_log_repository_mark_pushed_uses_domain_transition() -> None:
    row = _row()
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(row))
    session.flush = AsyncMock()
    repository = ReportLogRepository(session)

    await repository.mark_pushed(7)

    assert row.status == "pushed"
    assert row.pushed_at is not None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_log_repository_get_latest_returns_domain_record() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(_row(id=8, report_type="weekly")))
    repository = ReportLogRepository(session)

    record = await repository.get_latest("weekly")

    assert isinstance(record, AnalysisReportLogRecord)
    assert record.id == 8
    assert record.report_kind.value == "weekly"
