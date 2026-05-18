"""Application use case for LLM circuit-breaker administration."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional, Protocol


@dataclass(frozen=True, slots=True)
class CircuitBreakerStatus:
    """Circuit-breaker status read model."""

    state: str
    failures: int
    failure_threshold: int
    recovery_timeout: int
    last_failure_time: Optional[str]


class CircuitBreakerGateway(Protocol):
    def get_circuit_breaker_stats(self) -> dict:
        """Return current circuit-breaker statistics."""

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to closed state."""


class CircuitBreakerAdminUseCase:
    """Application use case for circuit-breaker operational commands."""

    def __init__(self, *, gateway: CircuitBreakerGateway):
        self._gateway = gateway

    def get_status(self) -> CircuitBreakerStatus:
        stats = self._gateway.get_circuit_breaker_stats()
        return CircuitBreakerStatus(
            state=stats["state"],
            failures=stats.get("failures", stats.get("failure_count", 0)),
            failure_threshold=stats["failure_threshold"],
            recovery_timeout=stats["recovery_timeout"],
            last_failure_time=_format_last_failure_time(stats.get("last_failure_time")),
        )

    def reset(self) -> None:
        self._gateway.reset_circuit_breaker()


def _format_last_failure_time(value: object) -> Optional[str]:
    """Normalize circuit-breaker timestamps for the public API contract."""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).isoformat()
    return str(value)
