"""
Unit Tests - ReportService

Tests for work package aggregation and report generation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from agents.pjm_agent.core.report_service import ReportService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def op_client():
    return AsyncMock()


@pytest.fixture
def bitable():
    mock = AsyncMock()
    mock.list_all_records = AsyncMock(return_value=[])
    return mock


class FakeCardRenderer:
    def build_daily_report_card(self, stats: dict) -> dict:
        return {"kind": "daily", "total": stats["total"]}

    def build_weekly_report_card(self, stats: dict) -> dict:
        return {"kind": "weekly", "total": stats["total"]}


@pytest.fixture
def service(op_client, bitable):
    return ReportService(
        op_client=op_client,
        bitable=bitable,
        card_renderer=FakeCardRenderer(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wp(
    wp_id: int,
    subject: str,
    status: str = "In Progress",
    project: str = "ProjectA",
    assignee: str = "Alice",
    progress: int = 50,
    due_date: str | None = None,
) -> dict:
    """Build a raw OP work package dict (API format)."""
    return {
        "id": wp_id,
        "subject": subject,
        "percentageDone": progress,
        "dueDate": due_date,
        "_links": {
            "status": {"title": status},
            "project": {"title": project},
            "assignee": {"title": assignee},
        },
    }


# ---------------------------------------------------------------------------
# _extract_wp_fields tests
# ---------------------------------------------------------------------------


class TestExtractWpFields:
    def test_extracts_all_fields(self, service):
        wp = _make_wp(
            1, "Build API", status="In Progress", project="Alpha", assignee="Bob", progress=30
        )
        result = service._extract_wp_fields(wp)
        assert result["id"] == 1
        assert result["subject"] == "Build API"
        assert result["status"] == "In Progress"
        assert result["project"] == "Alpha"
        assert result["assignee"] == "Bob"
        assert result["progress"] == 30

    def test_missing_assignee_defaults(self, service):
        wp = {
            "id": 2,
            "subject": "No assignee",
            "percentageDone": 0,
            "dueDate": None,
            "_links": {
                "status": {"title": "New"},
                "project": {"title": "Beta"},
                "assignee": {"title": ""},
            },
        }
        result = service._extract_wp_fields(wp)
        assert result["assignee"] == "未分配"


# ---------------------------------------------------------------------------
# _aggregate tests
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_basic_aggregation(self, service):
        wps = [
            {
                "id": 1,
                "subject": "A",
                "status": "In Progress",
                "project": "P1",
                "assignee": "Alice",
                "progress": 50,
                "due_date": None,
            },
            {
                "id": 2,
                "subject": "B",
                "status": "Done",
                "project": "P1",
                "assignee": "Bob",
                "progress": 100,
                "due_date": None,
            },
            {
                "id": 3,
                "subject": "C",
                "status": "In Progress",
                "project": "P2",
                "assignee": "Alice",
                "progress": 20,
                "due_date": None,
            },
        ]
        stats = service._aggregate(wps, [])
        assert stats["total"] == 3
        assert stats["by_status"]["In Progress"] == 2
        assert stats["by_status"]["Done"] == 1
        assert stats["avg_progress"] == 57  # (50+100+20)/3 = 56.67 -> 57
        assert "P1" in stats["by_project"]
        assert stats["by_project"]["P1"]["total"] == 2
        assert "Alice" in stats["by_assignee"]
        assert stats["by_assignee"]["Alice"]["total"] == 2

    def test_empty_list(self, service):
        stats = service._aggregate([], [])
        assert stats["total"] == 0
        assert stats["avg_progress"] == 0
        assert stats["overdue"] == []

    def test_overdue_detection(self, service):
        wps = [
            {
                "id": 1,
                "subject": "Overdue task",
                "status": "In Progress",
                "project": "P1",
                "assignee": "Alice",
                "progress": 30,
                "due_date": "2020-01-01",
            },
            {
                "id": 2,
                "subject": "Not overdue (done)",
                "status": "Done",
                "project": "P1",
                "assignee": "Bob",
                "progress": 100,
                "due_date": "2020-01-01",
            },
            {
                "id": 3,
                "subject": "Future due",
                "status": "In Progress",
                "project": "P1",
                "assignee": "Alice",
                "progress": 10,
                "due_date": "2099-12-31",
            },
        ]
        stats = service._aggregate(wps, [])
        assert len(stats["overdue"]) == 1
        assert stats["overdue"][0]["id"] == 1

    def test_overdue_capped_at_10(self, service):
        wps = [
            {
                "id": i,
                "subject": f"Task {i}",
                "status": "New",
                "project": "P",
                "assignee": "A",
                "progress": 0,
                "due_date": "2020-01-01",
            }
            for i in range(15)
        ]
        stats = service._aggregate(wps, [])
        assert len(stats["overdue"]) == 10


# ---------------------------------------------------------------------------
# generate_daily / generate_weekly integration
# ---------------------------------------------------------------------------


class TestGenerateReports:
    @pytest.mark.asyncio
    @patch("agents.pjm_agent.core.report_service.settings")
    async def test_generate_daily_returns_card_and_stats(self, mock_settings, service, op_client):
        mock_settings.decompose_project_ids = "1"
        mock_settings.feishu_pm_app_token = ""
        mock_settings.feishu_pm_task_table_id = ""
        op_client.get_work_packages = AsyncMock(
            return_value=[
                _make_wp(1, "Task A", status="In Progress", progress=50),
                _make_wp(2, "Task B", status="Done", progress=100),
            ]
        )

        result = await service.generate_daily()

        assert "card" in result
        assert "stats" in result
        assert result["stats"]["total"] == 2

    @pytest.mark.asyncio
    @patch("agents.pjm_agent.core.report_service.settings")
    async def test_generate_weekly_returns_card_and_stats(self, mock_settings, service, op_client):
        mock_settings.decompose_project_ids = "1"
        mock_settings.feishu_pm_app_token = ""
        mock_settings.feishu_pm_task_table_id = ""
        op_client.get_work_packages = AsyncMock(
            return_value=[
                _make_wp(1, "Task A", status="In Progress", progress=50),
            ]
        )

        result = await service.generate_weekly()

        assert "card" in result
        assert "stats" in result
        assert result["stats"]["total"] == 1

    @pytest.mark.asyncio
    @patch("agents.pjm_agent.core.report_service.settings")
    async def test_generate_daily_empty_project_ids(self, mock_settings, service, op_client):
        mock_settings.decompose_project_ids = ""
        mock_settings.feishu_pm_app_token = ""
        mock_settings.feishu_pm_task_table_id = ""

        result = await service.generate_daily()

        assert result["stats"]["total"] == 0
        op_client.get_work_packages.assert_not_awaited()
