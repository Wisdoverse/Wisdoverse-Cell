"""
AgentLoopCircuitBreaker unit tests.

Coverage:
1. State transitions: CLOSED → HALF_OPEN → OPEN → manual reset → CLOSED.
2. No-progress detection via no_progress_threshold.
3. Repeated-error detection via same_error_threshold.
4. Redis persistence across instance recovery.
5. State transition history.
6. Manual reset.
"""
import pytest

fakeredis = pytest.importorskip("fakeredis")
fakeredis_aioredis = fakeredis.aioredis

from shared.infra.agent_loop_breaker import AgentLoopCircuitBreaker
from shared.infra.circuit_breaker import CircuitState
from shared.infra.metrics import (
    LOOP_BREAKER_NO_PROGRESS_ROUNDS,
    LOOP_BREAKER_STATE,
    LOOP_BREAKER_TRIPS_TOTAL,
)


@pytest.fixture
async def redis():
    """Fake async Redis for testing."""
    r = fakeredis_aioredis.FakeRedis()
    yield r
    await r.aclose()


@pytest.fixture
async def breaker(redis):
    """Default breaker with low thresholds for testing."""
    return AgentLoopCircuitBreaker(
        agent_id="test-agent",
        no_progress_threshold=3,
        same_error_threshold=5,
        half_open_threshold=2,
        redis=redis,
    )


class TestInitialState:
    @pytest.mark.asyncio
    async def test_starts_closed(self, breaker):
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_can_execute_when_closed(self, breaker):
        assert await breaker.can_execute() is True


class TestNoProgressDetection:
    @pytest.mark.asyncio
    async def test_progress_keeps_closed(self, breaker):
        await breaker.record_round(has_progress=True)
        await breaker.record_round(has_progress=True)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_progress_resets_no_progress_counter(self, breaker):
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False)
        # One progress round should reset the counter
        await breaker.record_round(has_progress=True)
        state = await breaker.get_state()
        assert state["no_progress_count"] == 0

    @pytest.mark.asyncio
    async def test_half_open_at_threshold_minus_one(self, breaker):
        """2 no-progress rounds (half_open_threshold=2) → HALF_OPEN."""
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.HALF_OPEN.value

    @pytest.mark.asyncio
    async def test_open_at_no_progress_threshold(self, breaker):
        """3 no-progress rounds (no_progress_threshold=3) → OPEN."""
        for _ in range(3):
            await breaker.record_round(has_progress=False)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.OPEN.value

    @pytest.mark.asyncio
    async def test_below_threshold_stays_closed(self, breaker):
        """1 no-progress round (below half_open_threshold=2) → stays CLOSED."""
        await breaker.record_round(has_progress=False)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_open_rejects_execution(self, breaker):
        for _ in range(3):
            await breaker.record_round(has_progress=False)
        assert await breaker.can_execute() is False


class TestHalfOpenRecovery:
    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_progress(self, breaker):
        """HALF_OPEN + progress → CLOSED."""
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.HALF_OPEN.value

        await breaker.record_round(has_progress=True)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_continued_no_progress(self, breaker):
        """HALF_OPEN + more no-progress → OPEN."""
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False)
        # Now HALF_OPEN, one more no-progress hits the threshold
        await breaker.record_round(has_progress=False)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.OPEN.value


class TestSameErrorDetection:
    @pytest.mark.asyncio
    async def test_same_error_threshold_opens(self, breaker):
        """5 consecutive identical errors → OPEN."""
        for _ in range(5):
            await breaker.record_round(has_progress=False, error_signature="ValueError:bad")
        state = await breaker.get_state()
        assert state["state"] == CircuitState.OPEN.value

    @pytest.mark.asyncio
    async def test_different_errors_reset_counter(self, breaker):
        """Different error signatures reset the same-error counter."""
        for _ in range(4):
            await breaker.record_round(has_progress=False, error_signature="ValueError:bad")
        # Different error resets the counter
        await breaker.record_round(has_progress=False, error_signature="TypeError:other")
        state = await breaker.get_state()
        # Should NOT be OPEN from same_error (might be HALF_OPEN from no_progress)
        assert state["same_error_count"] == 1

    @pytest.mark.asyncio
    async def test_error_with_progress_still_tracks(self, breaker):
        """Error signature tracked even when there is progress."""
        for _ in range(5):
            await breaker.record_round(has_progress=True, error_signature="ValueError:bad")
        state = await breaker.get_state()
        assert state["state"] == CircuitState.OPEN.value


class TestManualReset:
    @pytest.mark.asyncio
    async def test_reset_from_open(self, breaker):
        for _ in range(3):
            await breaker.record_round(has_progress=False)
        assert await breaker.can_execute() is False

        await breaker.reset(reason="manual test")
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value
        assert state["no_progress_count"] == 0
        assert state["same_error_count"] == 0
        assert await breaker.can_execute() is True

    @pytest.mark.asyncio
    async def test_reset_on_closed_is_noop(self, breaker):
        await breaker.reset(reason="no-op test")
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value


class TestGetState:
    @pytest.mark.asyncio
    async def test_returns_correct_snapshot(self, breaker):
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False, error_signature="Err:x")

        state = await breaker.get_state()
        assert state["agent_id"] == "test-agent"
        assert state["no_progress_count"] == 2
        assert state["same_error_count"] == 1
        assert state["last_error_signature"] == "Err:x"
        assert "total_opens" in state


class TestRedisPersistence:
    @pytest.mark.asyncio
    async def test_state_survives_new_instance(self, redis):
        """State persists across breaker instances via Redis."""
        b1 = AgentLoopCircuitBreaker(
            agent_id="persist-agent", no_progress_threshold=3,
            same_error_threshold=5, half_open_threshold=2, redis=redis,
        )
        await b1.record_round(has_progress=False)
        await b1.record_round(has_progress=False)

        # New instance, same agent_id and redis
        b2 = AgentLoopCircuitBreaker(
            agent_id="persist-agent", no_progress_threshold=3,
            same_error_threshold=5, half_open_threshold=2, redis=redis,
        )
        state = await b2.get_state()
        assert state["state"] == CircuitState.HALF_OPEN.value
        assert state["no_progress_count"] == 2


class TestHistory:
    @pytest.mark.asyncio
    async def test_history_records_transitions(self, breaker, redis):
        # CLOSED → HALF_OPEN (2 no-progress)
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=False)
        # HALF_OPEN → OPEN (1 more no-progress)
        await breaker.record_round(has_progress=False)

        history = await redis.lrange("loop_breaker:test-agent:history", 0, -1)
        # Should have at least 2 transitions: CLOSED→HALF_OPEN, HALF_OPEN→OPEN
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_history_capped_at_50(self, breaker, redis):
        """History list should not grow beyond 50 entries."""
        # Generate many transitions: open → reset → open → reset ...
        for _ in range(30):
            for __ in range(3):
                await breaker.record_round(has_progress=False)
            await breaker.reset(reason="cycle")

        history = await redis.lrange("loop_breaker:test-agent:history", 0, -1)
        assert len(history) <= 50


class TestPrometheusMetrics:
    @pytest.mark.asyncio
    async def test_state_gauge_reflects_open(self, breaker):
        for _ in range(3):
            await breaker.record_round(has_progress=False)
        assert LOOP_BREAKER_STATE.labels(agent_id="test-agent")._value.get() == 2  # OPEN

    @pytest.mark.asyncio
    async def test_trips_counter_increments(self, breaker):
        before = LOOP_BREAKER_TRIPS_TOTAL.labels(agent_id="test-agent", reason="no_progress")._value.get()
        for _ in range(3):
            await breaker.record_round(has_progress=False)
        after = LOOP_BREAKER_TRIPS_TOTAL.labels(agent_id="test-agent", reason="no_progress")._value.get()
        assert after > before

    @pytest.mark.asyncio
    async def test_no_progress_gauge_tracks_count(self, breaker):
        await breaker.record_round(has_progress=False)
        assert LOOP_BREAKER_NO_PROGRESS_ROUNDS.labels(agent_id="test-agent")._value.get() == 1
        await breaker.record_round(has_progress=True)
        assert LOOP_BREAKER_NO_PROGRESS_ROUNDS.labels(agent_id="test-agent")._value.get() == 0


class TestOutputDeclineDetection:
    """Tests for output decline detection (E2)."""

    @pytest.fixture
    async def decline_breaker(self, redis):
        """Breaker configured for output decline detection testing."""
        return AgentLoopCircuitBreaker(
            agent_id="decline-agent",
            no_progress_threshold=10,  # high so no-progress won't interfere
            same_error_threshold=10,
            half_open_threshold=5,
            output_decline_threshold=0.3,
            output_decline_rounds=3,
            redis=redis,
        )

    @pytest.mark.asyncio
    async def test_decline_skipped_when_no_output_length(self, decline_breaker):
        """output_length=None -> decline detection silently skipped."""
        for _ in range(5):
            await decline_breaker.record_round(has_progress=True)
        state = await decline_breaker.get_state()
        assert state["output_decline_count"] == 0

    @pytest.mark.asyncio
    async def test_no_decline_with_stable_output(self, decline_breaker):
        """5 rounds of output_length=1000 -> no decline detected."""
        for _ in range(5):
            await decline_breaker.record_round(has_progress=True, output_length=1000)
        state = await decline_breaker.get_state()
        assert state["output_decline_count"] == 0
        assert state["state"] == CircuitState.CLOSED.value

    @pytest.mark.asyncio
    async def test_decline_detected_after_3_rounds(self, decline_breaker):
        """3 stable rounds, then 3 declining -> output_decline_count >= 3, OPEN."""
        # Establish baseline
        for _ in range(3):
            await decline_breaker.record_round(has_progress=True, output_length=1000)
        # Sharp decline
        for _ in range(3):
            await decline_breaker.record_round(has_progress=True, output_length=50)
        state = await decline_breaker.get_state()
        assert state["output_decline_count"] >= 3
        assert state["state"] == CircuitState.OPEN.value

    @pytest.mark.asyncio
    async def test_decline_resets_on_recovery(self, decline_breaker):
        """3 stable, 2 declining, then 1 recovery -> output_decline_count == 0."""
        for _ in range(3):
            await decline_breaker.record_round(has_progress=True, output_length=1000)
        # 2 declining rounds
        for _ in range(2):
            await decline_breaker.record_round(has_progress=True, output_length=50)
        # Recovery: output close to the mean of previous (which includes 1000s)
        await decline_breaker.record_round(has_progress=True, output_length=900)
        state = await decline_breaker.get_state()
        assert state["output_decline_count"] == 0

    @pytest.mark.asyncio
    async def test_decline_needs_minimum_3_data_points(self, decline_breaker):
        """Only 2 data points -> not enough to compute decline."""
        await decline_breaker.record_round(has_progress=True, output_length=1000)
        await decline_breaker.record_round(has_progress=True, output_length=50)
        state = await decline_breaker.get_state()
        assert state["output_decline_count"] == 0

    @pytest.mark.asyncio
    async def test_existing_tests_pass_without_output_length(self, redis):
        """Backward compat: record_round(has_progress=True) still works."""
        breaker = AgentLoopCircuitBreaker(
            agent_id="compat-agent",
            no_progress_threshold=3,
            same_error_threshold=5,
            half_open_threshold=2,
            redis=redis,
        )
        await breaker.record_round(has_progress=True)
        await breaker.record_round(has_progress=False)
        await breaker.record_round(has_progress=True)
        state = await breaker.get_state()
        assert state["state"] == CircuitState.CLOSED.value
        assert state["no_progress_count"] == 0
