"""Analysis-owned Feishu task snapshot and ACL translation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .projection import SubtaskProgressProjection


class AnalysisFeishuTaskStatus(StrEnum):
    """Analysis published-language status for Feishu task records."""

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    OTHER = "other"


_TITLE_FIELD = "任务(动宾短语)"
_STATUS_FIELD = "状态"
_BLOCKED_REASON_FIELD = "阻塞原因"


@dataclass(frozen=True, slots=True)
class AnalysisFeishuTaskSnapshot:
    """Analysis-local snapshot translated from one Feishu Bitable task row."""

    title: str
    status_label: str
    status: AnalysisFeishuTaskStatus
    blocked_reason: str = ""
    record_id: str | None = None

    @classmethod
    def from_bitable_record(
        cls,
        record: Mapping[str, Any],
    ) -> "AnalysisFeishuTaskSnapshot":
        fields = record.get("fields", {})
        if not isinstance(fields, Mapping):
            fields = {}
        record_id = _field_text(record, "record_id") or _field_text(record, "id")
        return cls.from_fields(fields, record_id=record_id or None)

    @classmethod
    def from_fields(
        cls,
        fields: Mapping[str, Any],
        *,
        record_id: str | None = None,
    ) -> "AnalysisFeishuTaskSnapshot":
        status_label = _field_text(fields, _STATUS_FIELD)
        title = _field_text(fields, _TITLE_FIELD) or "未命名"
        blocked_reason = _field_text(fields, _BLOCKED_REASON_FIELD)
        return cls(
            title=title,
            status_label=status_label,
            status=_classify_status(status_label),
            blocked_reason=blocked_reason,
            record_id=record_id,
        )

    @classmethod
    def from_projection(
        cls,
        projection: SubtaskProgressProjection,
    ) -> "AnalysisFeishuTaskSnapshot":
        status = (
            AnalysisFeishuTaskStatus.COMPLETED
            if projection.completed
            else _classify_status(projection.subtask_status)
        )
        return cls(
            title=projection.title or "未命名",
            status_label=projection.subtask_status,
            status=status,
            blocked_reason=projection.blocked_reason,
            record_id=projection.subtask_record_id,
        )

    @property
    def is_completed(self) -> bool:
        return self.status is AnalysisFeishuTaskStatus.COMPLETED

    @property
    def is_in_progress(self) -> bool:
        return self.status is AnalysisFeishuTaskStatus.IN_PROGRESS

    @property
    def is_blocked(self) -> bool:
        return self.status is AnalysisFeishuTaskStatus.BLOCKED

    @property
    def blocked_reason_or_default(self) -> str:
        return self.blocked_reason or "未说明"


class AnalysisFeishuTaskACL:
    """Translate Feishu Bitable task records into Analysis snapshots."""

    def from_bitable_records(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> list[AnalysisFeishuTaskSnapshot]:
        return [AnalysisFeishuTaskSnapshot.from_bitable_record(record) for record in records]

    def from_projection_rows(
        self,
        projections: Sequence[SubtaskProgressProjection],
    ) -> list[AnalysisFeishuTaskSnapshot]:
        return [
            AnalysisFeishuTaskSnapshot.from_projection(projection)
            for projection in projections
        ]


def _field_text(fields: Mapping[str, Any], key: str) -> str:
    return _coerce_text(fields.get(key)).strip()


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("text", "name", "value", "zh_cn", "en_us"):
            text = _coerce_text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, Sequence) and not isinstance(value, str):
        return ", ".join(text for item in value if (text := _coerce_text(item)))
    return str(value)


def _classify_status(status_label: str) -> AnalysisFeishuTaskStatus:
    normalized = status_label.casefold()
    if "阻塞" in status_label or "blocked" in normalized:
        return AnalysisFeishuTaskStatus.BLOCKED
    if "完成" in status_label or "done" in normalized or "completed" in normalized:
        return AnalysisFeishuTaskStatus.COMPLETED
    if "进行中" in status_label or "progress" in normalized:
        return AnalysisFeishuTaskStatus.IN_PROGRESS
    return AnalysisFeishuTaskStatus.OTHER


__all__ = [
    "AnalysisFeishuTaskACL",
    "AnalysisFeishuTaskSnapshot",
    "AnalysisFeishuTaskStatus",
]
