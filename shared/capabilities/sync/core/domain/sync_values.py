"""Sync capability value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, NewType

from shared.core.identifiers import OpenProjectProjectId, WorkPackageId

SyncMappingId = NewType("SyncMappingId", int)
SyncSubtaskMappingId = NewType("SyncSubtaskMappingId", int)
FeishuRecordId = NewType("FeishuRecordId", str)
FeishuSubtaskStatus = NewType("FeishuSubtaskStatus", str)

COMPLETED_SUBTASK_STATUSES: frozenset[FeishuSubtaskStatus] = frozenset(
    FeishuSubtaskStatus(value)
    for value in (
        "已完成",
        "完成",
        "Done",
        "Closed",
        "已关闭",
    )
)


class SyncMappingConflictError(ValueError):
    """Raised when Sync detects an inconsistent mapping projection."""


class SyncMappingAction(str, Enum):
    """Projection action for one OpenProject work package mapping."""

    CREATE = "create"
    UPDATE = "update"


@dataclass(frozen=True, slots=True)
class WorkPackageData:
    """Normalized OpenProject work-package data for Sync."""

    op_id: WorkPackageId
    title: str
    description: str | None = None
    status: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    progress: int = 0
    priority: str | None = None
    project_id: OpenProjectProjectId | None = None
    parent_id: WorkPackageId | None = None

    def __post_init__(self) -> None:
        if int(self.op_id) <= 0:
            raise ValueError("work package id must be positive")
        if not self.title:
            raise ValueError("work package title is required")
        if not 0 <= self.progress <= 100:
            raise ValueError("work package progress must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class FeishuRecordData:
    """Normalized Feishu Bitable record data for Sync."""

    record_id: FeishuRecordId | None = None
    op_id: WorkPackageId | None = None
    title: str | None = None
    subtask_name: str | None = None
    subtask_status: FeishuSubtaskStatus | None = None
    parent_op_id: WorkPackageId | None = None


@dataclass(frozen=True, slots=True)
class SyncMappingRecord:
    """Persisted OpenProject-to-Feishu mapping exposed to Sync core code."""

    id: SyncMappingId | None
    op_work_package_id: WorkPackageId
    feishu_record_id: FeishuRecordId | None
    op_project_id: OpenProjectProjectId | None = None
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id is not None and int(self.id) <= 0:
            raise ValueError("sync mapping id must be positive")
        if int(self.op_work_package_id) <= 0:
            raise ValueError("sync mapping work package id must be positive")

    @classmethod
    def from_record(cls, row: Any) -> "SyncMappingRecord":
        """Hydrate a mapping record from a persistence row."""
        raw_id = getattr(row, "id", None)
        raw_project_id = getattr(row, "op_project_id", None)
        return cls(
            id=SyncMappingId(int(raw_id)) if raw_id is not None else None,
            op_work_package_id=WorkPackageId(int(row.op_work_package_id)),
            feishu_record_id=feishu_record_id(getattr(row, "feishu_record_id", None)),
            op_project_id=(
                OpenProjectProjectId(int(raw_project_id))
                if raw_project_id is not None
                else None
            ),
            title=getattr(row, "title", None),
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )


@dataclass(frozen=True, slots=True)
class SyncMappingDecision:
    """Domain decision for projecting one work package into Feishu."""

    op_work_package_id: WorkPackageId
    action: SyncMappingAction
    feishu_record_id: FeishuRecordId | None
    op_project_id: OpenProjectProjectId | None
    title: str

    @property
    def should_update_record(self) -> bool:
        return self.action is SyncMappingAction.UPDATE

    @property
    def should_create_record(self) -> bool:
        return self.action is SyncMappingAction.CREATE


@dataclass(frozen=True, slots=True)
class FeishuSubtaskRollupItem:
    """Domain subtask snapshot used for parent progress rollups."""

    parent_op_id: WorkPackageId
    feishu_record_id: FeishuRecordId
    subtask_name: str | None = None
    subtask_status: FeishuSubtaskStatus | None = None

    def progress_payload(self) -> dict[str, Any]:
        """Return the minimal progress payload expected by legacy callers."""
        return {
            "subtask_name": self.subtask_name,
            "subtask_status": self.subtask_status,
        }


@dataclass(frozen=True, slots=True)
class ParentSubtaskRollup:
    """Grouped Feishu subtasks for one OpenProject parent work package."""

    parent_op_id: WorkPackageId
    subtasks: tuple[FeishuSubtaskRollupItem, ...]

    def __post_init__(self) -> None:
        if int(self.parent_op_id) <= 0:
            raise ValueError("rollup parent work package id must be positive")
        if not self.subtasks:
            raise ValueError("rollup requires at least one subtask")
        for subtask in self.subtasks:
            if subtask.parent_op_id != self.parent_op_id:
                raise SyncMappingConflictError(
                    "rollup contains a subtask for a different parent"
                )

    @property
    def completed_subtask_count(self) -> int:
        return sum(
            1
            for subtask in self.subtasks
            if is_completed_subtask_status(subtask.subtask_status)
        )

    @property
    def progress_percent(self) -> int:
        return round(self.completed_subtask_count / len(self.subtasks) * 100)

    def progress_payloads(self) -> list[dict[str, Any]]:
        """Return payloads compatible with the progress calculator API."""
        return [subtask.progress_payload() for subtask in self.subtasks]


class SyncProjectionPolicy:
    """Domain policy for Sync mapping and parent/subtask rollup consistency."""

    def decide_work_package_projection(
        self,
        *,
        wp_data: WorkPackageData,
        mapping: SyncMappingRecord | None,
    ) -> SyncMappingDecision:
        """Decide whether a work package should create or update a Feishu row."""
        if mapping is None:
            return SyncMappingDecision(
                op_work_package_id=wp_data.op_id,
                action=SyncMappingAction.CREATE,
                feishu_record_id=None,
                op_project_id=wp_data.project_id,
                title=wp_data.title,
            )

        if mapping.op_work_package_id != wp_data.op_id:
            raise SyncMappingConflictError(
                "mapping work package id does not match projection work package id"
            )
        if (
            mapping.op_project_id is not None
            and wp_data.project_id is not None
            and mapping.op_project_id != wp_data.project_id
        ):
            raise SyncMappingConflictError(
                "mapping project id does not match projection project id"
            )
        if mapping.feishu_record_id is None:
            return SyncMappingDecision(
                op_work_package_id=wp_data.op_id,
                action=SyncMappingAction.CREATE,
                feishu_record_id=None,
                op_project_id=wp_data.project_id,
                title=wp_data.title,
            )

        return SyncMappingDecision(
            op_work_package_id=wp_data.op_id,
            action=SyncMappingAction.UPDATE,
            feishu_record_id=mapping.feishu_record_id,
            op_project_id=wp_data.project_id,
            title=wp_data.title,
        )

    def subtask_rollup_item(
        self,
        record_data: FeishuRecordData,
    ) -> FeishuSubtaskRollupItem | None:
        """Return a rollup item for parent-linked Feishu records."""
        if record_data.parent_op_id is None:
            return None
        if record_data.record_id is None:
            raise SyncMappingConflictError(
                "parent-linked Feishu subtask requires a record id"
            )
        return FeishuSubtaskRollupItem(
            parent_op_id=record_data.parent_op_id,
            feishu_record_id=record_data.record_id,
            subtask_name=record_data.subtask_name,
            subtask_status=record_data.subtask_status,
        )

    def parent_rollups(
        self,
        subtasks: list[FeishuSubtaskRollupItem],
    ) -> list[ParentSubtaskRollup]:
        """Group subtask rollup items by OpenProject parent id."""
        grouped: dict[WorkPackageId, list[FeishuSubtaskRollupItem]] = {}
        for subtask in subtasks:
            grouped.setdefault(subtask.parent_op_id, []).append(subtask)
        return [
            ParentSubtaskRollup(parent_op_id=parent_id, subtasks=tuple(items))
            for parent_id, items in grouped.items()
        ]


@dataclass(frozen=True, slots=True)
class SubtaskMappingRecord:
    """Persisted Feishu subtask mapping exposed to Sync core code."""

    id: SyncSubtaskMappingId | None
    parent_op_id: WorkPackageId
    feishu_record_id: FeishuRecordId
    subtask_name: str | None = None
    subtask_status: FeishuSubtaskStatus | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id is not None and int(self.id) <= 0:
            raise ValueError("sync subtask mapping id must be positive")
        if int(self.parent_op_id) <= 0:
            raise ValueError("sync subtask parent work package id must be positive")
        if not str(self.feishu_record_id).strip():
            raise ValueError("sync subtask Feishu record id must not be empty")

    @classmethod
    def from_record(cls, row: Any) -> "SubtaskMappingRecord":
        """Hydrate a subtask mapping record from a persistence row."""
        raw_id = getattr(row, "id", None)
        normalized_record_id = feishu_record_id(row.feishu_record_id)
        if normalized_record_id is None:
            raise ValueError("sync subtask Feishu record id must not be empty")
        return cls(
            id=SyncSubtaskMappingId(int(raw_id)) if raw_id is not None else None,
            parent_op_id=WorkPackageId(int(row.parent_op_id)),
            feishu_record_id=normalized_record_id,
            subtask_name=getattr(row, "subtask_name", None),
            subtask_status=feishu_subtask_status(getattr(row, "subtask_status", None)),
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )


def feishu_record_id(raw: object) -> FeishuRecordId | None:
    """Normalize a raw Feishu record id."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return FeishuRecordId(value)


def feishu_subtask_status(raw: object) -> FeishuSubtaskStatus | None:
    """Normalize a raw Feishu subtask status."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return FeishuSubtaskStatus(value)


def is_completed_subtask_status(
    status: FeishuSubtaskStatus | str | None,
) -> bool:
    """Return whether a Feishu subtask status means completed."""
    normalized = feishu_subtask_status(status)
    return normalized in COMPLETED_SUBTASK_STATUSES


__all__ = [
    "COMPLETED_SUBTASK_STATUSES",
    "FeishuRecordData",
    "FeishuRecordId",
    "FeishuSubtaskStatus",
    "FeishuSubtaskRollupItem",
    "ParentSubtaskRollup",
    "SubtaskMappingRecord",
    "SyncMappingId",
    "SyncMappingAction",
    "SyncMappingConflictError",
    "SyncMappingDecision",
    "SyncMappingRecord",
    "SyncProjectionPolicy",
    "SyncSubtaskMappingId",
    "WorkPackageData",
    "feishu_record_id",
    "feishu_subtask_status",
    "is_completed_subtask_status",
]
