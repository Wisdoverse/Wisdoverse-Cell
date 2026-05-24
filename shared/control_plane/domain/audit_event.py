"""AuditEvent aggregate root and append-only evidence policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..models import AuditEvent as AuditEventRecord
from .metadata import ControlPlaneMetadata


class InvalidAuditEventError(ValueError):
    """Raised when an AuditEvent violates append-only ledger invariants."""


def clean_audit_text(value: Any, field_name: str) -> str:
    """Return required audit text without surrounding whitespace."""
    cleaned = str(value or "").strip()
    if not cleaned:
        raise InvalidAuditEventError(f"{field_name}_required")
    return cleaned


def clean_optional_audit_text(value: Any) -> str | None:
    """Return optional audit text, treating blank strings as absent."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def clean_audit_actor_type(value: Any) -> str:
    """Return the actor type, defaulting blank values to the system actor."""
    cleaned = str(value or "").strip()
    return cleaned or "system"


def clean_audit_actor_id(value: Any) -> str:
    """Return the actor identifier, preserving the empty system actor value."""
    return str(value or "").strip()


def clean_audit_detail(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-friendly audit detail mapping."""
    return ControlPlaneMetadata.from_mapping(value).as_dict()


@dataclass
class AuditEvent:
    """AuditEvent aggregate root for append-only operator evidence."""

    record: AuditEventRecord

    @classmethod
    def for_append(cls, record: AuditEventRecord) -> AuditEvent:
        aggregate = cls(record=record)
        aggregate._normalize_append_record()
        return aggregate

    @classmethod
    def from_record(cls, record: AuditEventRecord) -> AuditEvent:
        aggregate = cls(record=record)
        aggregate._normalize_append_record()
        return aggregate

    @property
    def audit_event_id(self) -> str:
        return self.record.audit_event_id

    @property
    def idempotency_key(self) -> str | None:
        return self.record.idempotency_key

    def _normalize_append_record(self) -> None:
        self.record = self.record.model_copy(
            update={
                "audit_event_id": clean_audit_text(
                    self.record.audit_event_id,
                    "audit_event_id",
                ),
                "company_id": clean_audit_text(self.record.company_id, "company_id"),
                "action": clean_audit_text(self.record.action, "action"),
                "target_type": clean_audit_text(
                    self.record.target_type,
                    "target_type",
                ),
                "target_id": clean_audit_text(self.record.target_id, "target_id"),
                "actor_type": clean_audit_actor_type(self.record.actor_type),
                "actor_id": clean_audit_actor_id(self.record.actor_id),
                "trace_id": clean_optional_audit_text(self.record.trace_id),
                "run_id": clean_optional_audit_text(self.record.run_id),
                "work_item_id": clean_optional_audit_text(self.record.work_item_id),
                "idempotency_key": clean_optional_audit_text(
                    self.record.idempotency_key
                ),
                "detail": clean_audit_detail(self.record.detail),
            }
        )


__all__ = [
    "AuditEvent",
    "InvalidAuditEventError",
    "clean_audit_actor_id",
    "clean_audit_actor_type",
    "clean_audit_detail",
    "clean_audit_text",
    "clean_optional_audit_text",
]
