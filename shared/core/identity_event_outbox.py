"""Identity domain-event to integration-event mapping."""

from __future__ import annotations

from shared.schemas.event import Event, EventMetadata, EventTypes

from .identity_domain import (
    IdentityDomainEvent,
    PlatformLinked,
    UserActivated,
    UserCreated,
)

IDENTITY_EVENT_SOURCE_AGENT = "identity-user"


def identity_event_from_domain_event(event: IdentityDomainEvent) -> Event:
    """Build a PII-safe integration event from an identity domain event."""
    payload = {
        "user_id": str(event.user_id),
        "domain_event": event.event_name,
        "occurred_at": event.occurred_at.isoformat(),
    }
    if isinstance(event, UserCreated):
        payload["email_present"] = event.email is not None
        payload["phone_present"] = event.phone is not None
        event_type = EventTypes.IDENTITY_USER_CREATED
    elif isinstance(event, PlatformLinked):
        payload["platform"] = event.platform.value
        event_type = EventTypes.IDENTITY_PLATFORM_LINKED
    elif isinstance(event, UserActivated):
        payload["platform"] = event.platform.value
        event_type = EventTypes.IDENTITY_USER_ACTIVATED
    else:
        raise TypeError(f"unsupported identity domain event: {type(event).__name__}")

    return Event(
        event_type=event_type,
        timestamp=event.occurred_at,
        source_agent=IDENTITY_EVENT_SOURCE_AGENT,
        payload=payload,
        schema_version="1.0",
        metadata=EventMetadata(
            correlation_id=_identity_event_correlation_id(event),
        ),
    )


def _identity_event_correlation_id(event: IdentityDomainEvent) -> str:
    return f"{event.event_name}:{event.user_id}:{event.occurred_at.isoformat()}"


__all__ = [
    "IDENTITY_EVENT_SOURCE_AGENT",
    "identity_event_from_domain_event",
]
