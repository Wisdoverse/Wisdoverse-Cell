"""Sync mapping domain-record tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from shared.capabilities.sync.core.domain.sync_values import (
    FeishuRecordData,
    FeishuRecordId,
    FeishuSubtaskStatus,
    SubtaskMappingRecord,
    SyncMappingAction,
    SyncMappingConflictError,
    SyncMappingId,
    SyncMappingRecord,
    SyncProjectionPolicy,
    SyncSubtaskMappingId,
    WorkPackageData,
)
from shared.core.identifiers import OpenProjectProjectId, WorkPackageId


def test_sync_mapping_record_hydrates_typed_identity_values() -> None:
    row = SimpleNamespace(
        id=10,
        op_work_package_id=123,
        feishu_record_id="rec_123",
        op_project_id=7,
        title="Mapped task",
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
        updated_at=datetime(2026, 5, 24, tzinfo=UTC),
    )

    record = SyncMappingRecord.from_record(row)

    assert record.id == SyncMappingId(10)
    assert record.op_work_package_id == WorkPackageId(123)
    assert record.feishu_record_id == FeishuRecordId("rec_123")
    assert record.op_project_id == OpenProjectProjectId(7)
    assert record.title == "Mapped task"


def test_subtask_mapping_record_hydrates_status_value_object() -> None:
    row = SimpleNamespace(
        id=11,
        parent_op_id=123,
        feishu_record_id="rec_sub",
        subtask_name="Subtask",
        subtask_status="完成",
        created_at=datetime(2026, 5, 23, tzinfo=UTC),
        updated_at=datetime(2026, 5, 24, tzinfo=UTC),
    )

    record = SubtaskMappingRecord.from_record(row)

    assert record.id == SyncSubtaskMappingId(11)
    assert record.parent_op_id == WorkPackageId(123)
    assert record.feishu_record_id == FeishuRecordId("rec_sub")
    assert record.subtask_status == FeishuSubtaskStatus("完成")


def test_mapping_records_reject_invalid_identity_values() -> None:
    with pytest.raises(ValueError):
        SyncMappingRecord(
            id=SyncMappingId(0),
            op_work_package_id=WorkPackageId(1),
            feishu_record_id=FeishuRecordId("rec_1"),
        )

    with pytest.raises(ValueError):
        SubtaskMappingRecord(
            id=SyncSubtaskMappingId(1),
            parent_op_id=WorkPackageId(0),
            feishu_record_id=FeishuRecordId("rec_1"),
        )

    with pytest.raises(ValueError):
        SubtaskMappingRecord(
            id=SyncSubtaskMappingId(1),
            parent_op_id=WorkPackageId(1),
            feishu_record_id=FeishuRecordId(" "),
        )


def test_sync_projection_policy_decides_create_or_update_mapping() -> None:
    policy = SyncProjectionPolicy()
    wp_data = WorkPackageData(
        op_id=WorkPackageId(123),
        project_id=OpenProjectProjectId(7),
        title="Mapped task",
    )

    create_decision = policy.decide_work_package_projection(
        wp_data=wp_data,
        mapping=None,
    )
    assert create_decision.action is SyncMappingAction.CREATE
    assert create_decision.should_create_record is True
    assert create_decision.feishu_record_id is None

    update_decision = policy.decide_work_package_projection(
        wp_data=wp_data,
        mapping=SyncMappingRecord(
            id=SyncMappingId(1),
            op_work_package_id=WorkPackageId(123),
            feishu_record_id=FeishuRecordId("rec_123"),
            op_project_id=OpenProjectProjectId(7),
            title="Old title",
        ),
    )
    assert update_decision.action is SyncMappingAction.UPDATE
    assert update_decision.should_update_record is True
    assert update_decision.feishu_record_id == FeishuRecordId("rec_123")


def test_sync_projection_policy_rejects_mapping_conflicts() -> None:
    policy = SyncProjectionPolicy()
    wp_data = WorkPackageData(
        op_id=WorkPackageId(123),
        project_id=OpenProjectProjectId(7),
        title="Mapped task",
    )

    with pytest.raises(SyncMappingConflictError):
        policy.decide_work_package_projection(
            wp_data=wp_data,
            mapping=SyncMappingRecord(
                id=SyncMappingId(1),
                op_work_package_id=WorkPackageId(999),
                feishu_record_id=FeishuRecordId("rec_123"),
                op_project_id=OpenProjectProjectId(7),
            ),
        )

    with pytest.raises(SyncMappingConflictError):
        policy.decide_work_package_projection(
            wp_data=wp_data,
            mapping=SyncMappingRecord(
                id=SyncMappingId(1),
                op_work_package_id=WorkPackageId(123),
                feishu_record_id=FeishuRecordId("rec_123"),
                op_project_id=OpenProjectProjectId(8),
            ),
        )


def test_sync_projection_policy_groups_parent_subtask_rollups() -> None:
    policy = SyncProjectionPolicy()
    first = policy.subtask_rollup_item(
        FeishuRecordData(
            record_id=FeishuRecordId("rec_a"),
            parent_op_id=WorkPackageId(123),
            subtask_name="A",
            subtask_status=FeishuSubtaskStatus("完成"),
        )
    )
    second = policy.subtask_rollup_item(
        FeishuRecordData(
            record_id=FeishuRecordId("rec_b"),
            parent_op_id=WorkPackageId(123),
            subtask_name="B",
            subtask_status=FeishuSubtaskStatus("进行中"),
        )
    )
    ignored = policy.subtask_rollup_item(
        FeishuRecordData(
            record_id=FeishuRecordId("rec_root"),
            parent_op_id=None,
            subtask_name="Root",
        )
    )

    assert ignored is None
    assert first is not None
    assert second is not None
    [rollup] = policy.parent_rollups([first, second])
    assert rollup.parent_op_id == WorkPackageId(123)
    assert rollup.progress_percent == 50
    assert rollup.progress_payloads() == [
        {"subtask_name": "A", "subtask_status": FeishuSubtaskStatus("完成")},
        {"subtask_name": "B", "subtask_status": FeishuSubtaskStatus("进行中")},
    ]


def test_sync_projection_policy_rejects_parent_subtasks_without_record_id() -> None:
    policy = SyncProjectionPolicy()

    with pytest.raises(SyncMappingConflictError):
        policy.subtask_rollup_item(
            FeishuRecordData(
                record_id=None,
                parent_op_id=WorkPackageId(123),
                subtask_name="A",
            )
        )
