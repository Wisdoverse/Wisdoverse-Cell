"""Analysis risk and quality assessment value objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from .projection import SubtaskProgressProjection


class InvalidAnalysisAssessmentError(ValueError):
    """Raised when an Analysis assessment value is invalid."""


class AnalysisRiskSeverity(StrEnum):
    """Published severity vocabulary for Analysis risk signals."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    UNKNOWN = "unknown"

    @classmethod
    def from_value(cls, value: Any) -> "AnalysisRiskSeverity":
        text = str(value or "").strip().casefold()
        for severity in cls:
            if text == severity.value:
                return severity
        return cls.UNKNOWN


class AnalysisRiskType(StrEnum):
    """Supported Analysis milestone risk types."""

    BLOCKED_SUBTASKS = "blocked_subtasks"
    LOW_PROGRESS = "low_progress"
    CUSTOM = "custom"

    @classmethod
    def from_value(cls, value: Any) -> "AnalysisRiskType":
        text = str(value or "").strip()
        for risk_type in cls:
            if text == risk_type.value:
                return risk_type
        return cls.CUSTOM


class AnalysisQualityVerdict(StrEnum):
    """Published quality verdict vocabulary for deliverable assessment."""

    EXCELLENT = "优秀"
    ACCEPTABLE = "合格"
    NEEDS_IMPROVEMENT = "需改进"
    FAILED = "不合格"

    @classmethod
    def from_value(cls, value: Any) -> "AnalysisQualityVerdict":
        text = str(value or "").strip()
        for verdict in cls:
            if text == verdict.value:
                return verdict
        raise InvalidAnalysisAssessmentError("quality verdict is not supported")


_FEATURE_FIELD = "关联 Feature ID (关键字段)"
_TITLE_FIELD = "任务(动宾短语)"
_STATUS_FIELD = "状态"
_DELIVERABLE_LINK_FIELD = "交付物/产出链接"
_QUALITY_FIELD = "交付物质量"
_QUALITY_COMMENT_FIELD = "质量评语"
_PROGRESS_FIELD = "进度"
_ACCEPTANCE_FIELDS = ("验收标准", "验收说明", "完成说明")


@dataclass(frozen=True, slots=True)
class AnalysisMilestoneTaskSnapshot:
    """Analysis-local snapshot for milestone risk checks."""

    feature_id: str
    title: str
    status_label: str

    @classmethod
    def from_fields(cls, fields: Mapping[str, Any]) -> "AnalysisMilestoneTaskSnapshot":
        feature_id = _field_text(fields, _FEATURE_FIELD).lstrip("#")
        return cls(
            feature_id=feature_id,
            title=_field_text(fields, _TITLE_FIELD),
            status_label=_field_text(fields, _STATUS_FIELD),
        )

    @classmethod
    def from_projection(
        cls,
        projection: SubtaskProgressProjection,
    ) -> "AnalysisMilestoneTaskSnapshot":
        return cls(
            feature_id=(projection.feature_id or "").lstrip("#"),
            title=projection.title,
            status_label=projection.subtask_status,
        )

    @property
    def has_feature(self) -> bool:
        return bool(self.feature_id)

    @property
    def is_blocked(self) -> bool:
        status = self.status_label.casefold()
        return "阻塞" in self.status_label or "blocked" in status

    @property
    def is_completed(self) -> bool:
        status = self.status_label.casefold()
        return (
            "完成" in self.status_label
            or "done" in status
            or "completed" in status
        )


@dataclass(frozen=True, slots=True)
class MilestoneRiskSignal:
    """Domain value object for one Analysis milestone risk."""

    feature_id: str
    risk_type: AnalysisRiskType
    severity: AnalysisRiskSeverity
    message: str
    blocked_tasks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        feature_id = self.feature_id.strip().lstrip("#")
        message = self.message.strip()
        if not message:
            raise InvalidAnalysisAssessmentError("risk message is required")
        object.__setattr__(self, "feature_id", feature_id)
        object.__setattr__(self, "message", message)
        object.__setattr__(
            self,
            "blocked_tasks",
            tuple(task for task in self.blocked_tasks if task),
        )

    @classmethod
    def blocked_subtasks(
        cls,
        *,
        feature_id: str,
        total: int,
        blocked_tasks: list[str],
    ) -> "MilestoneRiskSignal":
        normalized_feature_id = feature_id.strip().lstrip("#")
        severity = (
            AnalysisRiskSeverity.CRITICAL
            if len(blocked_tasks) > 1
            else AnalysisRiskSeverity.WARNING
        )
        return cls(
            feature_id=normalized_feature_id,
            risk_type=AnalysisRiskType.BLOCKED_SUBTASKS,
            severity=severity,
            message=(
                f"Feature #{normalized_feature_id}: "
                f"{len(blocked_tasks)}/{total} 子任务阻塞"
            ),
            blocked_tasks=tuple(blocked_tasks),
        )

    @classmethod
    def low_progress(
        cls,
        *,
        feature_id: str,
        completed: int,
        total: int,
    ) -> "MilestoneRiskSignal":
        if total <= 0:
            raise InvalidAnalysisAssessmentError("risk total must be positive")
        normalized_feature_id = feature_id.strip().lstrip("#")
        percent = int(completed / total * 100)
        return cls(
            feature_id=normalized_feature_id,
            risk_type=AnalysisRiskType.LOW_PROGRESS,
            severity=AnalysisRiskSeverity.WARNING,
            message=(
                f"Feature #{normalized_feature_id}: "
                f"完成率 {completed}/{total} ({percent}%)"
            ),
        )

    @classmethod
    def from_event_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> "MilestoneRiskSignal":
        severity = AnalysisRiskSeverity.from_value(
            payload.get("severity") or payload.get("risk_level")
        )
        risk_type = AnalysisRiskType.from_value(payload.get("type"))
        blocked_tasks = payload.get("blocked_tasks") or []
        if not isinstance(blocked_tasks, list):
            blocked_tasks = []
        return cls(
            feature_id=str(payload.get("feature_id") or payload.get("feature") or ""),
            risk_type=risk_type,
            severity=severity,
            message=str(payload.get("message") or risk_type.value),
            blocked_tasks=tuple(str(task) for task in blocked_tasks),
        )

    @property
    def notification_icon(self) -> str:
        if self.severity is AnalysisRiskSeverity.CRITICAL:
            return "🔴"
        if self.severity is AnalysisRiskSeverity.WARNING:
            return "🟡"
        return "ℹ️"

    def to_event_payload(self) -> dict[str, Any]:
        """Return the existing primitive risk payload shape."""
        payload: dict[str, Any] = {
            "feature_id": self.feature_id,
            "type": self.risk_type.value,
            "severity": self.severity.value,
            "risk_level": self.severity.value,
            "message": self.message,
        }
        if self.blocked_tasks:
            payload["blocked_tasks"] = list(self.blocked_tasks)
        return payload


@dataclass(frozen=True, slots=True)
class DeliverableQualityTask:
    """Analysis-local snapshot for one deliverable quality review candidate."""

    record_id: str | None
    name: str
    deliverable_link: str
    status_label: str = ""
    acceptance_hint: str = ""
    progress_label: str = ""

    @classmethod
    def from_bitable_record(
        cls,
        record: Mapping[str, Any],
    ) -> "DeliverableQualityTask | None":
        fields = record.get("fields", {})
        if not isinstance(fields, Mapping):
            fields = {}
        deliverable_link = _field_text(fields, _DELIVERABLE_LINK_FIELD)
        existing_quality = _field_text(fields, _QUALITY_FIELD)
        if not deliverable_link or existing_quality:
            return None
        return cls(
            record_id=_field_text(record, "record_id") or None,
            name=_field_text(fields, _TITLE_FIELD),
            deliverable_link=deliverable_link,
            status_label=_field_text(fields, _STATUS_FIELD),
            acceptance_hint=_first_field_text(fields, _ACCEPTANCE_FIELDS),
            progress_label=_field_text(fields, _PROGRESS_FIELD),
        )

    def to_prompt_metadata(self) -> dict[str, Any]:
        """Return the quality-review metadata allowed into the LLM prompt."""
        return {
            "task_name": self.name,
            "status": self.status_label,
            "deliverable_link_present": bool(self.deliverable_link),
            "deliverable_link_domain": _safe_link_domain(self.deliverable_link),
            "acceptance_hint": self.acceptance_hint,
            "progress": self.progress_label,
        }


@dataclass(frozen=True, slots=True)
class QualityEvaluation:
    """Domain value object for a deliverable quality verdict."""

    verdict: AnalysisQualityVerdict
    comment: str
    confidence: float = 0.0

    def __post_init__(self) -> None:
        comment = self.comment.strip()
        if not comment:
            raise InvalidAnalysisAssessmentError("quality comment is required")
        if not 0 <= self.confidence <= 1:
            raise InvalidAnalysisAssessmentError("quality confidence must be 0..1")
        object.__setattr__(self, "comment", comment)

    @classmethod
    def from_llm_payload(cls, payload: Mapping[str, Any]) -> "QualityEvaluation":
        return cls(
            verdict=AnalysisQualityVerdict.from_value(payload.get("quality")),
            comment=str(payload.get("comment") or ""),
            confidence=float(payload.get("confidence") or 0.0),
        )

    @property
    def quality(self) -> str:
        return self.verdict.value

    def to_write_back_fields(self) -> dict[str, str]:
        return {
            _QUALITY_FIELD: self.quality,
            _QUALITY_COMMENT_FIELD: self.comment,
        }


@dataclass(frozen=True, slots=True)
class DeliverableQualityResult:
    """Domain value object for a completed deliverable quality review."""

    task: DeliverableQualityTask
    evaluation: QualityEvaluation
    write_back: bool

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "record_id": self.task.record_id,
            "task": self.task.name,
            "quality": self.evaluation.quality,
            "comment": self.evaluation.comment,
            "confidence": self.evaluation.confidence,
            "write_back": self.write_back,
        }


def _field_text(fields: Mapping[str, Any], key: str) -> str:
    return _coerce_text(fields.get(key)).strip()


def _first_field_text(fields: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        text = _field_text(fields, key)
        if text:
            return text
    return ""


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
    if isinstance(value, list | tuple):
        return ", ".join(text for item in value if (text := _coerce_text(item)))
    return str(value)


def _safe_link_domain(link: str) -> str:
    try:
        parsed = urlparse(link)
    except ValueError:
        return ""
    return parsed.netloc


__all__ = [
    "AnalysisMilestoneTaskSnapshot",
    "AnalysisQualityVerdict",
    "AnalysisRiskSeverity",
    "AnalysisRiskType",
    "DeliverableQualityResult",
    "DeliverableQualityTask",
    "InvalidAnalysisAssessmentError",
    "MilestoneRiskSignal",
    "QualityEvaluation",
]
