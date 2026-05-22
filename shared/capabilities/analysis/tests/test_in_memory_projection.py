"""Tests for the Analysis projection in-memory adapter (DDD-004 impl step)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shared.capabilities.analysis.core.domain.in_memory_projection import (
    InMemoryWorkPackageProjectionStore,
)
from shared.capabilities.analysis.core.domain.projection import (
    SubtaskProgressProjection,
    WorkPackageProjection,
    WorkPackageProjectionPort,
)


def _wp(wp_id: int, *, project_id: int = 1, when: datetime | None = None) -> WorkPackageProjection:
    return WorkPackageProjection(
        wp_id=wp_id,
        project_id=project_id,
        subject=f"WP {wp_id}",
        type_name="Task",
        status_name="In progress",
        percentage_done=50,
        assigned_to="usr_test",
        parent_id=None,
        due_date=None,
        updated_at=when or datetime(2026, 5, 22, tzinfo=UTC),
        extra={},
    )


def _subtask(record_id: str, *, parent_wp_id: int = 1, when: datetime | None = None) -> SubtaskProgressProjection:
    return SubtaskProgressProjection(
        parent_wp_id=parent_wp_id,
        subtask_record_id=record_id,
        subtask_status="Done",
        completed=True,
        updated_at=when or datetime(2026, 5, 22, tzinfo=UTC),
    )


def test_in_memory_adapter_satisfies_port_protocol() -> None:
    store = InMemoryWorkPackageProjectionStore()
    assert isinstance(store, WorkPackageProjectionPort)


@pytest.mark.asyncio
async def test_upsert_then_list_returns_latest_snapshot() -> None:
    store = InMemoryWorkPackageProjectionStore()
    store.upsert_work_package(_wp(42))
    listed = await store.list_work_packages()
    assert len(listed) == 1
    assert listed[0].wp_id == 42


@pytest.mark.asyncio
async def test_upsert_overwrites_prior_snapshot() -> None:
    """append/replace semantics per data-ownership.md §1.8."""
    store = InMemoryWorkPackageProjectionStore()
    store.upsert_work_package(_wp(42, when=datetime(2026, 5, 22, tzinfo=UTC)))
    store.upsert_work_package(
        WorkPackageProjection(
            wp_id=42,
            project_id=1,
            subject="WP 42 renamed",
            type_name="Task",
            status_name="Done",
            percentage_done=100,
            assigned_to=None,
            parent_id=None,
            due_date=None,
            updated_at=datetime(2026, 5, 23, tzinfo=UTC),
            extra={},
        )
    )
    listed = await store.list_work_packages()
    assert len(listed) == 1
    assert listed[0].percentage_done == 100
    assert listed[0].subject == "WP 42 renamed"


@pytest.mark.asyncio
async def test_filter_by_project_id() -> None:
    store = InMemoryWorkPackageProjectionStore()
    store.upsert_work_package(_wp(1, project_id=10))
    store.upsert_work_package(_wp(2, project_id=20))
    rows_10 = await store.list_work_packages(project_id=10)
    assert {r.wp_id for r in rows_10} == {1}


@pytest.mark.asyncio
async def test_filter_by_updated_since() -> None:
    store = InMemoryWorkPackageProjectionStore()
    store.upsert_work_package(_wp(1, when=datetime(2026, 5, 20, tzinfo=UTC)))
    store.upsert_work_package(_wp(2, when=datetime(2026, 5, 22, tzinfo=UTC)))
    rows = await store.list_work_packages(updated_since=datetime(2026, 5, 21, tzinfo=UTC))
    assert {r.wp_id for r in rows} == {2}


@pytest.mark.asyncio
async def test_subtask_upsert_and_list() -> None:
    store = InMemoryWorkPackageProjectionStore()
    store.upsert_subtask(_subtask("rec_a", parent_wp_id=42))
    store.upsert_subtask(_subtask("rec_b", parent_wp_id=99))
    rows_42 = await store.list_subtask_progress(parent_wp_id=42)
    assert {r.subtask_record_id for r in rows_42} == {"rec_a"}
