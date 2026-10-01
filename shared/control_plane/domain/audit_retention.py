"""Pure audit export retention, redaction, and bounded serialization policy."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from ..models import AuditEvent

DEFAULT_AUDIT_RETENTION_DAYS = 90
MAX_AUDIT_RETENTION_DAYS = 3650
MAX_DETAIL_DEPTH = 8
MAX_DETAIL_ITEMS = 100
MAX_DETAIL_STRING_LENGTH = 4096

_SENSITIVE_KEY = re.compile(
    r"(?i)(?:secret|token|password|passwd|auth(?:orization)?|cookie|credential|"
    r"api[_-]?key|private[_-]?key|session[_-]?key)"
)
_FREEFORM_KEY = re.compile(
    r"(?i)(?:^|[_-])(?:body|request|response|prompt|message|content|text|note|"
    r"description|metadata|email|phone|address|name|user_agent|ip_address)(?:$|[_-])"
)
_LINKAGE_KEY = re.compile(r"(?i)(?:^|[_-])(?:id|ids|hash|checksum|digest)(?:$|[_-])")
_SECRET_VALUE = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
    r"|\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret|password|credential|"
    r"auth(?:orization)?|cookie)\b"
    r"\s*[:=]\s*[^\s,;]+"
)
_CREDENTIAL_URL = re.compile(r"(?i)\b(?:https?|ftp)://[^\s\]\[()<>\"']+")


class AuditRetentionError(ValueError):
    """Raised when an export window falls outside the permitted retention range."""


@dataclass(frozen=True, slots=True)
class AuditRetentionPolicy:
    retention_days: int = DEFAULT_AUDIT_RETENTION_DAYS
    oldest_exportable_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.retention_days, bool)
            or not 1 <= self.retention_days <= MAX_AUDIT_RETENTION_DAYS
        ):
            raise AuditRetentionError("invalid_retention_days")

    def to_dict(self) -> dict[str, Any]:
        return {
            "retention_days": self.retention_days,
            "oldest_exportable_at": _iso(self.oldest_exportable_at)
            if self.oldest_exportable_at
            else None,
        }


@dataclass(frozen=True, slots=True)
class SanitizedAuditEvent:
    """Deeply immutable audit event projection safe for export."""

    audit_event_id: str
    company_id: str
    action: str
    target_type: str
    target_id: str
    actor_type: str
    actor_id: str
    trace_id: str | None
    run_id: str | None
    work_item_id: str | None
    idempotency_key: str | None
    detail: Mapping[str, Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_event_id": self.audit_event_id,
            "company_id": self.company_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "work_item_id": self.work_item_id,
            "idempotency_key": self.idempotency_key,
            "detail": _thaw(self.detail),
            "created_at": _iso(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class AuditEventExport:
    company_id: str
    since: datetime
    until: datetime
    retention_policy: AuditRetentionPolicy
    events: tuple[SanitizedAuditEvent, ...]
    source_counts: tuple[tuple[str, int], ...]

    @property
    def total(self) -> int:
        return len(self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "since": _iso(self.since),
            "until": _iso(self.until),
            "retention_policy": self.retention_policy.to_dict(),
            "source_counts": {key: count for key, count in self.source_counts},
            "total": self.total,
            "audit_events": [event.to_dict() for event in self.events],
        }


def export_audit_events(
    records: Iterable[AuditEvent],
    *,
    company_id: str,
    since: datetime,
    until: datetime,
    retention_days: int = DEFAULT_AUDIT_RETENTION_DAYS,
    now: datetime | None = None,
) -> AuditEventExport:
    """Filter by exact company and an in-retention time window, then redact immutably."""
    company = company_id.strip()
    if not company:
        raise AuditRetentionError("company_id_required")
    current = _require_aware(now or datetime.now(UTC), "now")
    start = _require_aware(since, "since")
    end = _require_aware(until, "until")
    if start > end or end > current:
        raise AuditRetentionError("invalid_export_window")
    if isinstance(retention_days, bool) or not 1 <= retention_days <= MAX_AUDIT_RETENTION_DAYS:
        raise AuditRetentionError("invalid_retention_days")
    oldest = current - timedelta(days=retention_days)
    if start < oldest:
        raise AuditRetentionError("export_window_outside_retention")

    selected = [record for record in records if record.company_id == company]
    selected = [record for record in selected if start <= _as_utc(record.created_at) <= end]
    selected.sort(key=lambda record: (_as_utc(record.created_at), record.audit_event_id))
    events = tuple(_sanitize_event(record) for record in selected)
    counts = Counter(event.actor_type for event in events)
    return AuditEventExport(
        company_id=company,
        since=start,
        until=end,
        retention_policy=AuditRetentionPolicy(retention_days, oldest),
        events=events,
        source_counts=tuple(sorted(counts.items())),
    )


def sanitize_audit_detail(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a deterministic deeply immutable, bounded redaction of audit detail."""
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise AuditRetentionError("audit_detail_must_be_object")
    sanitized = _sanitize_value(value, depth=0)
    return sanitized if isinstance(sanitized, Mapping) else MappingProxyType({})


def audit_detail_for_storage(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-compatible copy of the immutable sanitized detail."""
    return dict(_thaw(sanitize_audit_detail(value)))


def _sanitize_event(record: AuditEvent) -> SanitizedAuditEvent:
    return SanitizedAuditEvent(
        audit_event_id=record.audit_event_id,
        company_id=record.company_id,
        action=record.action,
        target_type=record.target_type,
        target_id=record.target_id,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        trace_id=record.trace_id,
        run_id=record.run_id,
        work_item_id=record.work_item_id,
        idempotency_key=record.idempotency_key,
        detail=sanitize_audit_detail(record.detail),
        created_at=_as_utc(record.created_at),
    )


def _sanitize_value(value: Any, *, depth: int) -> Any:
    if depth > MAX_DETAIL_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        pairs: dict[str, Any] = {}
        items = sorted(value.items(), key=lambda item: str(item[0]))[:MAX_DETAIL_ITEMS]
        for raw_key, raw_value in items:
            key = str(raw_key)[:128]
            if _FREEFORM_KEY.search(key) and not _LINKAGE_KEY.search(key):
                continue
            if _SENSITIVE_KEY.search(key):
                pairs[key] = "[REDACTED]"
                continue
            pairs[key] = _sanitize_value(raw_value, depth=depth + 1)
        if len(value) > MAX_DETAIL_ITEMS:
            pairs["_truncated_items"] = len(value) - MAX_DETAIL_ITEMS
        return MappingProxyType(dict(sorted(pairs.items())))
    if isinstance(value, list | tuple):
        clipped = tuple(_sanitize_value(item, depth=depth + 1) for item in value[:MAX_DETAIL_ITEMS])
        if len(value) > MAX_DETAIL_ITEMS:
            return clipped + ("[TRUNCATED_ITEMS]",)
        return clipped
    if isinstance(value, str):
        return _redact_text(value[:MAX_DETAIL_STRING_LENGTH])
    if isinstance(value, Enum):
        return _sanitize_value(value.value, depth=depth)
    if isinstance(value, datetime):
        return _iso(_as_utc(value))
    if value is None or isinstance(value, bool | int | float):
        return value
    return "[UNSUPPORTED_VALUE]"


def _redact_text(value: str) -> str:
    text = _CREDENTIAL_URL.sub(_redact_url, value)
    return _SECRET_VALUE.sub("[REDACTED]", text)[:MAX_DETAIL_STRING_LENGTH]


def _redact_url(match: re.Match[str]) -> str:
    candidate = match.group(0).rstrip(".,;)")
    suffix = match.group(0)[len(candidate) :]
    try:
        parsed = urlsplit(candidate)
        if parsed.username is None and parsed.password is None:
            return match.group(0)
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        safe = f"{parsed.scheme}://[REDACTED]@{host}{parsed.path}"
        if parsed.query:
            safe += "?" + parsed.query
        if parsed.fragment:
            safe += "#" + parsed.fragment
        return safe + suffix
    except ValueError:
        return "[REDACTED_URL]" + suffix


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuditRetentionError(f"{field}_must_include_timezone")
    return value.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


__all__ = [
    "AuditEventExport",
    "AuditRetentionError",
    "AuditRetentionPolicy",
    "DEFAULT_AUDIT_RETENTION_DAYS",
    "SanitizedAuditEvent",
    "export_audit_events",
    "sanitize_audit_detail",
]
