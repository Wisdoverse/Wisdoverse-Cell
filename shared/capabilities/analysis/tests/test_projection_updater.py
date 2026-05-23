"""Unit tests for the projection-update consumer (DDD-004 follow-up)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from shared.capabilities.analysis.core.domain.in_memory_projection import (
    InMemoryWorkPackageProjectionStore,
)
from shared.capabilities.analysis.core.projection_updater import (
    ProjectionUpdater,
    _project_subtask,
    _project_work_package,
)


class _FakeOpenProject:
    def __init__(self, work_packages: list[dict[str, Any]]):
        self._work_packages = work_packages

    async def get_work_packages(
        self,
        project_id: int | None = None,
        filters: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        return list(self._work_packages)

    async def get_work_package(self, wp_id: int) -> dict[str, Any]:
        raise NotImplementedError

    async def update_work_package(
        self, wp_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def create_work_package(
        self, project_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        pass


class _FakeBitable:
    def __init__(self, records: list[dict[str, Any]]):
        self._records = records

    async def list_records(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        return {"items": list(self._records), "has_more": False}

    async def list_all_records(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        return list(self._records)

    async def create_record(self, *args, **kwargs) -> str:
        raise NotImplementedError

    async def update_record(self, *args, **kwargs) -> bool:
        raise NotImplementedError

    async def list_fields(self, *args, **kwargs) -> list[dict[str, Any]]:
        return []

    async def create_field(self, *args, **kwargs) -> dict[str, Any]:
        raise NotImplementedError


def _wp_dict(
    *,
    wp_id: int = 100,
    subject: str = "Test WP",
    project_id: int = 1,
    parent_id: int | None = None,
    status: str = "In progress",
    percentage: int = 25,
) -> dict[str, Any]:
    links: dict[str, Any] = {
        "project": {"href": f"/api/v3/projects/{project_id}", "title": "Project"},
        "status": {"title": status},
        "type": {"title": "Task"},
        "assignedTo": {"title": "alice"},
    }
    if parent_id is not None:
        links["parent"] = {"href": f"/api/v3/work_packages/{parent_id}"}
    return {
        "id": wp_id,
        "subject": subject,
        "percentageDone": percentage,
        "dueDate": "2026-05-30",
        "updatedAt": "2026-05-23T12:00:00Z",
        "_links": links,
    }


def test_project_work_package_translates_links_and_fields() -> None:
    projection = _project_work_package(_wp_dict(wp_id=42, parent_id=10))
    assert projection.wp_id == 42
    assert projection.parent_id == 10
    assert projection.project_id == 1
    assert projection.status_name == "In progress"
    assert projection.type_name == "Task"
    assert projection.assigned_to == "alice"
    assert projection.percentage_done == 25
    assert projection.due_date is not None
    assert projection.updated_at.tzinfo is not None


def test_project_work_package_handles_missing_links_gracefully() -> None:
    minimal = {"id": 7, "subject": "no links"}
    projection = _project_work_package(minimal)
    assert projection.wp_id == 7
    assert projection.project_id is None
    assert projection.parent_id is None
    assert projection.status_name == "unknown"


def test_project_subtask_returns_none_when_parent_missing() -> None:
    record = {"record_id": "rec_1", "fields": {}}
    assert _project_subtask(record) is None


def test_project_subtask_normalises_completed_flag() -> None:
    record = {
        "record_id": "rec_2",
        "fields": {"parent_op_id": "42", "subtask_status": "已完成"},
    }
    projection = _project_subtask(record)
    assert projection is not None
    assert projection.parent_wp_id == 42
    assert projection.completed is True


@pytest.mark.asyncio
async def test_refresh_work_packages_upserts_into_store() -> None:
    op = _FakeOpenProject([_wp_dict(wp_id=1), _wp_dict(wp_id=2, parent_id=1)])
    bitable = _FakeBitable([])
    store = InMemoryWorkPackageProjectionStore()
    updater = ProjectionUpdater(
        op_client=op, bitable=bitable, writer=store
    )

    upserted = await updater.refresh_work_packages()

    assert upserted == 2
    rows = await store.list_work_packages()
    assert sorted(r.wp_id for r in rows) == [1, 2]


@pytest.mark.asyncio
async def test_refresh_subtasks_upserts_when_parent_id_present() -> None:
    op = _FakeOpenProject([])
    bitable = _FakeBitable(
        [
            {
                "record_id": "rec_1",
                "fields": {"parent_op_id": "10", "subtask_status": "进行中"},
            },
            {
                "record_id": "rec_2",
                "fields": {"parent_op_id": None},
            },
        ]
    )
    store = InMemoryWorkPackageProjectionStore()
    updater = ProjectionUpdater(
        op_client=op, bitable=bitable, writer=store
    )

    upserted = await updater.refresh_subtasks()

    assert upserted == 1
    rows = await store.list_subtask_progress(parent_wp_id=10)
    assert len(rows) == 1
    assert rows[0].subtask_record_id == "rec_1"


@pytest.mark.asyncio
async def test_refresh_all_returns_per_kind_counts() -> None:
    op = _FakeOpenProject([_wp_dict(wp_id=1)])
    bitable = _FakeBitable(
        [
            {
                "record_id": "rec_1",
                "fields": {"parent_op_id": "1", "subtask_status": "Done"},
            }
        ]
    )
    store = InMemoryWorkPackageProjectionStore()
    updater = ProjectionUpdater(
        op_client=op, bitable=bitable, writer=store
    )

    result = await updater.refresh_all()

    assert result == {"work_packages": 1, "subtasks": 1}
