"""Structural tests for the Analysis projection seed (DDD-004)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from shared.capabilities.analysis.core.domain.projection import (
    SubtaskProgressProjection,
    WorkPackageProjection,
    WorkPackageProjectionPort,
)


def test_work_package_projection_is_frozen_value_object() -> None:
    proj = WorkPackageProjection(
        wp_id=42,
        project_id=1,
        subject="Migrate users table",
        type_name="Task",
        status_name="In progress",
        percentage_done=40,
        assigned_to="usr_alice",
        parent_id=None,
        due_date=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 22, tzinfo=UTC),
        extra={"priority": "high"},
    )
    other = WorkPackageProjection(**dataclasses.asdict(proj))
    assert proj == other
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.wp_id = 99  # type: ignore[misc]


def test_subtask_progress_projection_is_frozen_value_object() -> None:
    proj = SubtaskProgressProjection(
        parent_wp_id=42,
        subtask_record_id="rec_abc",
        subtask_status="Done",
        completed=True,
        updated_at=datetime(2026, 5, 22, tzinfo=UTC),
        title="Close Feature task",
        blocked_reason="",
        feature_id="2266",
    )
    other = SubtaskProgressProjection(**dataclasses.asdict(proj))
    assert proj == other
    assert proj.title == "Close Feature task"
    assert proj.feature_id == "2266"
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.completed = False  # type: ignore[misc]


def test_port_runtime_checkable_with_minimal_double() -> None:
    class _Double:
        async def list_work_packages(self, *, project_id=None, updated_since=None):
            return []

        async def list_subtask_progress(self, *, parent_wp_id=None, updated_since=None):
            return []

    assert isinstance(_Double(), WorkPackageProjectionPort)
