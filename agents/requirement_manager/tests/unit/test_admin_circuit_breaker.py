from datetime import UTC, datetime
from unittest.mock import MagicMock

from agents.requirement_manager.core.admin_circuit_breaker import (
    CircuitBreakerAdminUseCase,
)


def test_circuit_breaker_admin_normalizes_failure_count_and_timestamp():
    gateway = MagicMock()
    gateway.get_circuit_breaker_stats.return_value = {
        "state": "open",
        "failure_count": 3,
        "failure_threshold": 5,
        "recovery_timeout": 60,
        "last_failure_time": 1735689600,
    }

    status = CircuitBreakerAdminUseCase(gateway=gateway).get_status()

    assert status.state == "open"
    assert status.failures == 3
    assert status.last_failure_time == datetime.fromtimestamp(
        1735689600,
        UTC,
    ).isoformat()


def test_circuit_breaker_admin_resets_gateway():
    gateway = MagicMock()

    CircuitBreakerAdminUseCase(gateway=gateway).reset()

    gateway.reset_circuit_breaker.assert_called_once_with()
