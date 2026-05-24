"""Control Plane domain-event outbox mapping."""

from __future__ import annotations

from shared.schemas.event import Event, EventMetadata

from .domain.audit_event import clean_audit_detail
from .models import AuditEvent

CONTROL_PLANE_EVENT_SOURCE_AGENT = "control-plane"


def audit_event_carries_domain_event(event: AuditEvent) -> bool:
    """True when an audit row was built from an aggregate domain event."""
    return bool(event.detail.get("domain_event"))


def outbox_event_from_audit_event(event: AuditEvent) -> Event:
    """Build an integration event from a durable domain-event audit row."""
    detail = clean_audit_detail(event.detail)
    payload = {
        "audit_event_id": event.audit_event_id,
        "company_id": event.company_id,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "domain_event": detail.get("domain_event", event.action),
        "detail": detail,
    }
    if event.run_id:
        payload["run_id"] = event.run_id
    if event.work_item_id:
        payload["work_item_id"] = event.work_item_id

    return Event(
        event_type=event.action,
        timestamp=event.created_at,
        source_agent=CONTROL_PLANE_EVENT_SOURCE_AGENT,
        payload=payload,
        schema_version="1.0",
        metadata=EventMetadata(
            trace_id=event.trace_id,
            correlation_id=event.audit_event_id,
        ),
    )


__all__ = [
    "CONTROL_PLANE_EVENT_SOURCE_AGENT",
    "audit_event_carries_domain_event",
    "outbox_event_from_audit_event",
]
