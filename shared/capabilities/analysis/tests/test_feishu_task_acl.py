"""Analysis Feishu task ACL tests."""

from datetime import UTC, datetime

from shared.capabilities.analysis.core.domain.feishu_task import (
    AnalysisFeishuTaskACL,
    AnalysisFeishuTaskSnapshot,
    AnalysisFeishuTaskStatus,
)
from shared.capabilities.analysis.core.domain.projection import (
    SubtaskProgressProjection,
)


def test_feishu_task_snapshot_translates_bitable_fields() -> None:
    snapshot = AnalysisFeishuTaskSnapshot.from_bitable_record(
        {
            "record_id": "rec_1",
            "fields": {
                "任务(动宾短语)": [{"text": "完成设计"}],
                "状态": {"text": "已完成(Done)"},
                "阻塞原因": None,
            },
        }
    )

    assert snapshot.record_id == "rec_1"
    assert snapshot.title == "完成设计"
    assert snapshot.status is AnalysisFeishuTaskStatus.COMPLETED
    assert snapshot.is_completed is True
    assert snapshot.blocked_reason_or_default == "未说明"


def test_feishu_task_acl_classifies_blocked_before_in_progress() -> None:
    [snapshot] = AnalysisFeishuTaskACL().from_bitable_records(
        [
            {
                "id": "rec_2",
                "fields": {
                    "任务(动宾短语)": "部署服务",
                    "状态": "阻塞(Blocked) / 进行中(In Progress)",
                    "阻塞原因": "等待服务器",
                },
            }
        ]
    )

    assert snapshot.record_id == "rec_2"
    assert snapshot.status is AnalysisFeishuTaskStatus.BLOCKED
    assert snapshot.is_blocked is True
    assert snapshot.blocked_reason_or_default == "等待服务器"


def test_feishu_task_snapshot_defaults_missing_fields() -> None:
    snapshot = AnalysisFeishuTaskSnapshot.from_bitable_record({"fields": {}})

    assert snapshot.title == "未命名"
    assert snapshot.status is AnalysisFeishuTaskStatus.OTHER
    assert snapshot.record_id is None


def test_feishu_task_acl_translates_projection_rows() -> None:
    [snapshot] = AnalysisFeishuTaskACL().from_projection_rows(
        [
            SubtaskProgressProjection(
                parent_wp_id=42,
                subtask_record_id="rec_projection",
                subtask_status="阻塞(Blocked)",
                completed=False,
                updated_at=datetime.now(UTC),
                title="投影任务",
                blocked_reason="等待接口",
            )
        ]
    )

    assert snapshot.record_id == "rec_projection"
    assert snapshot.title == "投影任务"
    assert snapshot.is_blocked is True
    assert snapshot.blocked_reason_or_default == "等待接口"
