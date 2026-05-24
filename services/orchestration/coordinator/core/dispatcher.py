"""Convert Coordinator decisions into EventBus events."""
from shared.schemas.event import Event

from .domain.dispatch import CoordinatorDispatchPolicy
from .models import Decision

_DISPATCH_POLICY = CoordinatorDispatchPolicy()


def decision_to_event(decision: Decision) -> Event:
    """Convert a Decision into an Event the target Agent understands."""
    envelope = _DISPATCH_POLICY.envelope_for(decision)
    return Event.create(
        event_type=envelope.event_type,
        source_agent="coordinator",
        payload=dict(envelope.payload),
        trace_id=decision.trace_id,
    )
