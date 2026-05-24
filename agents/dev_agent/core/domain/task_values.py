"""Dev task value objects."""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Implementation risk classification owned by the Dev domain."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def risk_level_value(risk_level: RiskLevel | str | None) -> str:
    """Return the persisted string value for a risk classification."""
    if risk_level is None:
        return RiskLevel.MEDIUM.value
    if isinstance(risk_level, RiskLevel):
        return risk_level.value
    return RiskLevel(risk_level).value


__all__ = [
    "RiskLevel",
    "risk_level_value",
]
