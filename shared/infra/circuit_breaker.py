"""
Circuit Breaker - 断路器实现

防止对失败服务的持续调用，实现快速失败和自动恢复。

状态机:
    CLOSED (正常) → 失败达到阈值 → OPEN (断开)
    OPEN (断开) → 超时后 → HALF_OPEN (半开)
    HALF_OPEN (半开) → 成功 → CLOSED (正常)
    HALF_OPEN (半开) → 失败 → OPEN (断开)
"""
import time
from enum import Enum
from threading import Lock
from typing import Optional

from shared.utils.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitState(Enum):
    """断路器状态"""
    CLOSED = "closed"      # 正常状态，允许请求通过
    OPEN = "open"          # 断开状态，快速失败
    HALF_OPEN = "half_open"  # 半开状态，允许探测请求


class CircuitBreakerError(Exception):
    """断路器打开时抛出的异常"""

    def __init__(self, message: str = "Circuit breaker is open"):
        self.message = message
        super().__init__(self.message)


class CircuitBreaker:
    """
    断路器实现

    当连续失败次数达到阈值时，断路器打开，后续请求直接失败。
    经过恢复时间后，断路器进入半开状态，允许一个探测请求。
    如果探测成功，断路器关闭；如果失败，断路器重新打开。

    使用方式:
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

    线程安全: 是（使用 Lock）
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        name: str = "default"
    ):
        """
        初始化断路器

        Args:
            failure_threshold: 连续失败多少次后打开断路器
            recovery_timeout: 断路器打开后多少秒进入半开状态
            name: 断路器名称（用于日志）
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
        """获取当前状态"""
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        """获取当前失败计数"""
        with self._lock:
            return self._failure_count

    def can_execute(self) -> bool:
        """
        检查是否可以执行请求

        Returns:
            True: 可以执行
            False: 断路器打开，应该快速失败
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # 检查是否超过恢复时间
                if self._last_failure_time is None:
                    return True

                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    # 进入半开状态
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "circuit_breaker_half_open",
                        name=self.name,
                        elapsed_seconds=round(elapsed, 2)
                    )
                    return True

                return False

            # HALF_OPEN 状态，允许探测请求
            return True

    def record_success(self) -> None:
        """
        记录成功调用

        在 HALF_OPEN 状态下成功会关闭断路器。
        """
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # 探测成功，关闭断路器
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(
                    "circuit_breaker_closed",
                    name=self.name,
                    reason="probe_success"
                )
            elif self._state == CircuitState.CLOSED:
                # 重置失败计数
                self._failure_count = 0

    def record_failure(self) -> None:
        """
        记录失败调用

        连续失败达到阈值时打开断路器。
        在 HALF_OPEN 状态下失败会重新打开断路器。
        """
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # 探测失败，重新打开
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_reopened",
                    name=self.name,
                    reason="probe_failed"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # 达到阈值，打开断路器
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "circuit_breaker_opened",
                        name=self.name,
                        failure_count=self._failure_count,
                        threshold=self.failure_threshold
                    )

    def reset(self) -> None:
        """手动重置断路器到关闭状态"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            logger.info(
                "circuit_breaker_reset",
                name=self.name
            )

    def get_stats(self) -> dict:
        """获取断路器统计信息"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self._last_failure_time
            }
