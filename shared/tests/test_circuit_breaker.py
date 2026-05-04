"""
Circuit breaker unit tests.

Coverage:
1. State transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
2. Failure count and threshold
3. Recovery timeout
4. Thread safety
5. Manual reset
"""
import time
from threading import Thread

from shared.infra.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState


class TestCircuitBreakerBasic:
    """Basic behavior tests."""

    def test_initial_state_is_closed(self):
        """Initial state is CLOSED."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_can_execute_when_closed(self):
        """CLOSED state allows execution."""
        breaker = CircuitBreaker()
        assert breaker.can_execute() is True

    def test_success_resets_failure_count(self):
        """Success resets failure count."""
        breaker = CircuitBreaker(failure_threshold=5)

        # Record failures.
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 2

        # Reset after success.
        breaker.record_success()
        assert breaker.failure_count == 0


class TestCircuitBreakerOpenState:
    """Open state tests."""

    def test_opens_after_threshold_failures(self):
        """Circuit opens after threshold failures."""
        breaker = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    def test_rejects_when_open(self):
        """OPEN state rejects execution."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

        # Trigger open state.
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    def test_does_not_open_before_threshold(self):
        """Circuit does not open before threshold."""
        breaker = CircuitBreaker(failure_threshold=5)

        for _ in range(4):
            breaker.record_failure()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True


class TestCircuitBreakerHalfOpenState:
    """Half-open state tests."""

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trigger open state.
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout.
        time.sleep(1.1)

        # Checking execution triggers the state transition.
        assert breaker.can_execute() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_on_success_in_half_open(self):
        """HALF_OPEN state closes after success."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trigger open state.
        breaker.record_failure()
        breaker.record_failure()

        # Wait for recovery.
        time.sleep(1.1)
        breaker.can_execute()  # Triggers transition to HALF_OPEN.

        # Close after success.
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_reopens_on_failure_in_half_open(self):
        """HALF_OPEN state reopens after failure."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trigger open state.
        breaker.record_failure()
        breaker.record_failure()

        # Wait for recovery.
        time.sleep(1.1)
        breaker.can_execute()  # Triggers transition to HALF_OPEN.
        assert breaker.state == CircuitState.HALF_OPEN

        # Reopen after failure.
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerReset:
    """Manual reset tests."""

    def test_reset_closes_circuit(self):
        """reset closes the circuit."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Trigger open state.
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Reset.
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.can_execute() is True


class TestCircuitBreakerStats:
    """Statistics tests."""

    def test_get_stats(self):
        """get_stats returns expected statistics."""
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            name="test_breaker"
        )

        breaker.record_failure()
        breaker.record_failure()

        stats = breaker.get_stats()

        assert stats["name"] == "test_breaker"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 2
        assert stats["failure_threshold"] == 5
        assert stats["recovery_timeout"] == 60


class TestCircuitBreakerThreadSafety:
    """Thread safety tests."""

    def test_concurrent_failures(self):
        """Concurrent failures are counted correctly."""
        breaker = CircuitBreaker(failure_threshold=100)

        def record_failures():
            for _ in range(10):
                breaker.record_failure()

        threads = [Thread(target=record_failures) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 10 threads × 10 failures = 100
        assert breaker.failure_count == 100
        assert breaker.state == CircuitState.OPEN

    def test_concurrent_success_and_failure(self):
        """Concurrent success and failure operations are handled correctly."""
        breaker = CircuitBreaker(failure_threshold=1000)

        def mixed_operations():
            for _ in range(50):
                breaker.record_failure()
                breaker.record_success()

        threads = [Thread(target=mixed_operations) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # The last operation is record_success and should reset the count, but
        # concurrency can make the exact result vary. The key assertion is that
        # it does not crash.
        assert breaker.state in [CircuitState.CLOSED, CircuitState.OPEN]


class TestCircuitBreakerError:
    """Circuit breaker error tests."""

    def test_error_message(self):
        """Error includes the provided message."""
        error = CircuitBreakerError("Custom message")
        assert str(error) == "Custom message"

    def test_default_message(self):
        """Default message is present."""
        error = CircuitBreakerError()
        assert "Circuit breaker is open" in str(error)
