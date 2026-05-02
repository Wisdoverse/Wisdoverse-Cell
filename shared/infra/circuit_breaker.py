"""
Circuit Breaker implementation.

Prevents repeated calls to failing services and supports fail-fast behavior
with automatic recovery.

State machine:
    CLOSED (normal) -> failure threshold reached -> OPEN (fail fast)
    OPEN (fail fast) -> timeout elapsed -> HALF_OPEN (probe)
    HALF_OPEN (probe) -> success -> CLOSED (normal)
    HALF_OPEN (probe) -> failure -> OPEN (fail fast)
"""
import time
from enum import Enum
from threading import Lock
from typing import Optional

from shared.utils.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitState(Enum):
    """Circuit breaker state."""
    CLOSED = "closed"      # normal state, requests are allowed
    OPEN = "open"          # open state, requests fail fast
    HALF_OPEN = "half_open"  # probe state, a trial request is allowed


class CircuitBreakerError(Exception):
    """Raised when the circuit breaker is open."""

    def __init__(self, message: str = "Circuit breaker is open"):
        self.message = message
        super().__init__(self.message)


class CircuitBreaker:
    """
    Circuit breaker implementation.

    When consecutive failures reach the threshold, the breaker opens and
    later requests fail fast. After the recovery timeout, the breaker enters
    HALF_OPEN and allows a probe request. A successful probe closes the
    breaker; a failed probe reopens it.

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        if not breaker.can_execute():
            raise CircuitBreakerError()

        try:
            result = await call_external_service()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise

    Thread-safe: yes, through Lock.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        name: str = "default"
    ):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: Consecutive failure count that opens the breaker.
            recovery_timeout: Seconds before an open breaker enters HALF_OPEN.
            name: Breaker name used in logs.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        """Return the current state."""
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        """Return the current failure count."""
        with self._lock:
            return self._failure_count

    def can_execute(self) -> bool:
        """
        Check whether a request can execute.

        Returns:
            True: execution is allowed.
            False: the breaker is open and the caller should fail fast.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check whether recovery timeout has elapsed.
                if self._last_failure_time is None:
                    return True

                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    # Enter half-open state.
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "circuit_breaker_half_open",
                        name=self.name,
                        elapsed_seconds=round(elapsed, 2)
                    )
                    return True

                return False

            # HALF_OPEN state allows a probe request.
            return True

    def record_success(self) -> None:
        """
        Record a successful call.

        A success in HALF_OPEN closes the breaker.
        """
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Successful probe closes the breaker.
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(
                    "circuit_breaker_closed",
                    name=self.name,
                    reason="probe_success"
                )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count.
                self._failure_count = 0

    def record_failure(self) -> None:
        """
        Record a failed call.

        Consecutive failures open the breaker at the configured threshold.
        A failure in HALF_OPEN reopens the breaker.
        """
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failed probe reopens the breaker.
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_reopened",
                    name=self.name,
                    reason="probe_failed"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Threshold reached; open the breaker.
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "circuit_breaker_opened",
                        name=self.name,
                        failure_count=self._failure_count,
                        threshold=self.failure_threshold
                    )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            logger.info(
                "circuit_breaker_reset",
                name=self.name
            )

    def get_stats(self) -> dict:
        """Return circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self._last_failure_time
            }
