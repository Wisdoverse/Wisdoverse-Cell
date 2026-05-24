"""Base domain-event type for Control Plane aggregates."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


class ControlPlaneDomainEvent:
    """Base type for immutable in-memory Control Plane domain events."""

    @property
    def event_name(self) -> str:
        """Return the stable class-name event identifier."""
        return type(self).__name__

    def to_payload(self) -> dict[str, Any]:
        """Return a dictionary payload for future outbox/audit adapters."""
        if not is_dataclass(self):
            raise TypeError("domain event payload requires a dataclass event")
        return asdict(self)


__all__ = ["ControlPlaneDomainEvent"]
