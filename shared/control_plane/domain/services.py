"""Base contract for Control Plane domain services."""

from __future__ import annotations


class ControlPlaneDomainService:
    """Stateless domain service for rules spanning Control Plane aggregates."""

    __slots__ = ()

    @property
    def service_name(self) -> str:
        """Return the stable service name for architecture guards and logs."""
        return type(self).__name__


__all__ = [
    "ControlPlaneDomainService",
]
