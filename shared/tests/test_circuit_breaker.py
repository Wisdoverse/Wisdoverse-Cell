"""
断路器单元测试

测试覆盖:
1. 状态转换: CLOSED → OPEN → HALF_OPEN → CLOSED
2. 失败计数和阈值
3. 恢复超时
4. 线程安全
5. 手动重置
"""
import time
from threading import Thread

from shared.infra.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState


class TestCircuitBreakerBasic:
    """基础功能测试"""

    def test_initial_state_is_closed(self):
        """初始状态应为 CLOSED"""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_can_execute_when_closed(self):
        """CLOSED 状态应允许执行"""
        breaker = CircuitBreaker()
        assert breaker.can_execute() is True

    def test_success_resets_failure_count(self):
        """成功应重置失败计数"""
        breaker = CircuitBreaker(failure_threshold=5)

        # 记录一些失败
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 2

        # 成功后重置
        breaker.record_success()
        assert breaker.failure_count == 0


class TestCircuitBreakerOpenState:
    """断路器打开状态测试"""

    def test_opens_after_threshold_failures(self):
        """连续失败达到阈值后应打开"""
        breaker = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    def test_rejects_when_open(self):
        """OPEN 状态应拒绝执行"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

        # 触发打开
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    def test_does_not_open_before_threshold(self):
        """未达到阈值不应打开"""
        breaker = CircuitBreaker(failure_threshold=5)

        for _ in range(4):
            breaker.record_failure()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True


class TestCircuitBreakerHalfOpenState:
    """半开状态测试"""

    def test_transitions_to_half_open_after_timeout(self):
        """超时后应转换为 HALF_OPEN"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # 触发打开
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # 等待恢复超时
        time.sleep(1.1)

        # 检查是否可执行（会触发状态转换）
        assert breaker.can_execute() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_on_success_in_half_open(self):
        """HALF_OPEN 状态成功后应关闭"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # 触发打开
        breaker.record_failure()
        breaker.record_failure()

        # 等待恢复
        time.sleep(1.1)
        breaker.can_execute()  # 触发转换到 HALF_OPEN

        # 成功后关闭
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_reopens_on_failure_in_half_open(self):
        """HALF_OPEN 状态失败后应重新打开"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # 触发打开
        breaker.record_failure()
        breaker.record_failure()

        # 等待恢复
        time.sleep(1.1)
        breaker.can_execute()  # 触发转换到 HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

        # 失败后重新打开
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerReset:
    """手动重置测试"""

    def test_reset_closes_circuit(self):
        """reset 应关闭断路器"""
        breaker = CircuitBreaker(failure_threshold=2)

        # 触发打开
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # 重置
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.can_execute() is True


class TestCircuitBreakerStats:
    """统计信息测试"""

    def test_get_stats(self):
        """应返回正确的统计信息"""
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
    """线程安全测试"""

    def test_concurrent_failures(self):
        """并发失败应正确计数"""
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
        """并发成功和失败应正确处理"""
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

        # 最后一次操作是 record_success，应该重置计数
        # 但由于并发，实际结果可能不同
        # 关键是不应该崩溃
        assert breaker.state in [CircuitState.CLOSED, CircuitState.OPEN]


class TestCircuitBreakerError:
    """断路器异常测试"""

    def test_error_message(self):
        """异常应包含正确消息"""
        error = CircuitBreakerError("Custom message")
        assert str(error) == "Custom message"

    def test_default_message(self):
        """默认消息"""
        error = CircuitBreakerError()
        assert "Circuit breaker is open" in str(error)
