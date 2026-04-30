"""Deprecated: use shared.infra.circuit_breaker"""
from shared.infra.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState

__all__ = ["CircuitBreaker", "CircuitBreakerError", "CircuitState"]
