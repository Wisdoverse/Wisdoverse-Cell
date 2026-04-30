"""
Tests for EvolutionGuard — TDD: written before implementation.

Tests cover:
- No rollback when success rate is stable (within threshold)
- Rollback triggered when degradation > 10%
- No rollback with insufficient samples
- Circuit breaker triggers after 3+ rollbacks in 24h (sets paused flag)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.evolution.evolution_guard import EvolutionGuard

# ── Helpers ────────────────────────────────────────────────────────────────


def make_skill(success_rate: float, version: str = "2", promoted_at: object = "now"):
    """Return a mock SkillConfig with the given success_rate."""
    skill = MagicMock()
    skill.success_rate = success_rate
    skill.version = version
    skill.promoted_at = promoted_at
    return skill


def make_prev_skill(version: str = "1"):
    """Return a mock previous SkillConfig for rollback target."""
    skill = MagicMock()
    skill.version = version
    return skill


def make_traces(count: int) -> list:
    """Return a list of mock trace objects (contents don't matter for count checks)."""
    return [MagicMock() for _ in range(count)]


def make_repo(
    active_skill=None,
    traces=None,
    current_rate: float = 0.90,
    prev_skill=None,
) -> AsyncMock:
    """Build a fully mocked EvolutionRepository."""
    repo = AsyncMock()
    repo.get_active_skill = AsyncMock(return_value=active_skill)
    repo.get_recent_traces = AsyncMock(return_value=traces or [])
    repo.calc_success_rate = AsyncMock(return_value=current_rate)
    repo.promote_skill = AsyncMock(return_value=None)
    repo.get_previous_active = AsyncMock(return_value=prev_skill)
    return repo


def make_redis(rollback_count: int = 0) -> AsyncMock:
    """Build a mocked Redis client.

    incr() returns the new value after increment, so we simulate the value
    *after* an incr call by returning rollback_count + 1.
    expire() is a no-op.
    set() is a no-op.
    """
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=rollback_count + 1)
    redis.expire = AsyncMock(return_value=True)
    redis.set = AsyncMock(return_value=True)
    return redis


# ── No-rollback: stable performance ────────────────────────────────────────


class TestNoRollbackStable:
    """Guard should not roll back when performance is within the threshold."""

    @pytest.mark.asyncio
    async def test_no_rollback_when_rate_equal_baseline(self):
        """Exactly matching baseline → no rollback."""
        active = make_skill(success_rate=0.90)
        traces = make_traces(10)
        repo = make_repo(active_skill=active, traces=traces, current_rate=0.90)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis, rollback_threshold=0.10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rollback_within_threshold(self):
        """Degradation exactly at threshold (not exceeding) → no rollback."""
        active = make_skill(success_rate=0.90)
        traces = make_traces(10)
        # 0.90 - 0.80 = 0.10, which equals threshold (not strictly greater)
        repo = make_repo(active_skill=active, traces=traces, current_rate=0.80)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis, rollback_threshold=0.10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rollback_improved_performance(self):
        """Current rate better than baseline → no rollback."""
        active = make_skill(success_rate=0.80)
        traces = make_traces(15)
        repo = make_repo(active_skill=active, traces=traces, current_rate=0.95)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis, rollback_threshold=0.10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()


# ── No-rollback: guard conditions not met ──────────────────────────────────


class TestNoRollbackGuardConditions:
    """Guard should return False early when preconditions fail."""

    @pytest.mark.asyncio
    async def test_no_rollback_when_no_active_skill(self):
        """No active skill config → return False immediately."""
        repo = make_repo(active_skill=None)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.get_recent_traces.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rollback_when_never_promoted(self):
        """Active skill with promoted_at=None (never promoted) → return False."""
        active = make_skill(success_rate=0.90, promoted_at=None)
        repo = make_repo(active_skill=active)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.get_recent_traces.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rollback_insufficient_samples(self):
        """Fewer traces than min_samples → return False without rollback."""
        active = make_skill(success_rate=0.90)
        traces = make_traces(5)  # below min_samples=10
        repo = make_repo(active_skill=active, traces=traces, current_rate=0.50)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis, min_samples=10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rollback_exactly_min_samples_minus_one(self):
        """Exactly one fewer than min_samples → still not enough."""
        active = make_skill(success_rate=0.90)
        traces = make_traces(9)
        repo = make_repo(active_skill=active, traces=traces, current_rate=0.40)
        redis = make_redis()

        guard = EvolutionGuard(repo=repo, redis=redis, min_samples=10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()


# ── Rollback triggered ─────────────────────────────────────────────────────


class TestRollbackTriggered:
    """Guard should roll back when degradation exceeds threshold."""

    @pytest.mark.asyncio
    async def test_rollback_when_degradation_exceeds_threshold(self):
        """Degradation of 15% > 10% threshold → rollback triggered."""
        active = make_skill(success_rate=0.90, version="2")
        traces = make_traces(10)
        prev = make_prev_skill(version="1")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.75, prev_skill=prev
        )
        redis = make_redis(rollback_count=0)  # first rollback of the day

        guard = EvolutionGuard(
            repo=repo, redis=redis, rollback_threshold=0.10, max_rollbacks_per_day=3
        )
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is True
        repo.promote_skill.assert_awaited_once_with("decompose-task", "1")

    @pytest.mark.asyncio
    async def test_rollback_increments_redis_counter(self):
        """Successful rollback increments the Redis circuit breaker counter."""
        active = make_skill(success_rate=0.90, version="2")
        traces = make_traces(10)
        prev = make_prev_skill(version="1")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.70, prev_skill=prev
        )
        redis = make_redis(rollback_count=0)

        guard = EvolutionGuard(repo=repo, redis=redis, rollback_threshold=0.10)
        await guard.check("pjm-agent", "decompose-task")

        redis.incr.assert_awaited_once_with("evolution:rollback_count:pjm-agent")
        redis.expire.assert_awaited_once_with(
            "evolution:rollback_count:pjm-agent", 86400
        )

    @pytest.mark.asyncio
    async def test_rollback_calls_get_previous_active(self):
        """Guard fetches the previous active skill to roll back to."""
        active = make_skill(success_rate=0.90, version="3")
        traces = make_traces(10)
        prev = make_prev_skill(version="2")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.60, prev_skill=prev
        )
        redis = make_redis(rollback_count=0)

        guard = EvolutionGuard(repo=repo, redis=redis, rollback_threshold=0.10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is True
        repo.get_previous_active.assert_awaited_once_with("decompose-task")

    @pytest.mark.asyncio
    async def test_no_rollback_when_no_previous_skill(self):
        """Degradation detected but no previous skill to roll back to → return False."""
        active = make_skill(success_rate=0.90, version="1")
        traces = make_traces(10)
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.70, prev_skill=None
        )
        redis = make_redis(rollback_count=0)

        guard = EvolutionGuard(repo=repo, redis=redis, rollback_threshold=0.10)
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()


# ── Circuit breaker ────────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Guard must stop rolling back after max_rollbacks_per_day is reached."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_fires_after_max_rollbacks(self):
        """When rollback count exceeds max, set paused flag and return False."""
        active = make_skill(success_rate=0.90, version="2")
        traces = make_traces(10)
        prev = make_prev_skill(version="1")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.70, prev_skill=prev
        )
        # incr returns 4 — already over the limit of 3
        redis = make_redis(rollback_count=3)

        guard = EvolutionGuard(
            repo=repo, redis=redis, rollback_threshold=0.10, max_rollbacks_per_day=3
        )
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is False
        repo.promote_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_sets_paused_flag(self):
        """When circuit breaker fires, Redis paused flag is set."""
        active = make_skill(success_rate=0.90, version="2")
        traces = make_traces(10)
        prev = make_prev_skill(version="1")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.70, prev_skill=prev
        )
        redis = make_redis(rollback_count=3)  # incr → 4 > max_rollbacks_per_day=3

        guard = EvolutionGuard(
            repo=repo, redis=redis, rollback_threshold=0.10, max_rollbacks_per_day=3
        )
        await guard.check("pjm-agent", "decompose-task")

        redis.set.assert_awaited_once_with("evolution:paused:pjm-agent", "true")

    @pytest.mark.asyncio
    async def test_circuit_breaker_does_not_fire_at_limit(self):
        """Rollback count exactly at max_rollbacks_per_day still allows rollback."""
        active = make_skill(success_rate=0.90, version="2")
        traces = make_traces(10)
        prev = make_prev_skill(version="1")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.70, prev_skill=prev
        )
        # incr returns 3, max is 3: 3 > 3 is False → rollback proceeds
        redis = make_redis(rollback_count=2)

        guard = EvolutionGuard(
            repo=repo, redis=redis, rollback_threshold=0.10, max_rollbacks_per_day=3
        )
        result = await guard.check("pjm-agent", "decompose-task")

        assert result is True
        repo.promote_skill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_circuit_breaker_uses_agent_scoped_keys(self):
        """Redis keys are scoped per agent_id."""
        active = make_skill(success_rate=0.90, version="2")
        traces = make_traces(10)
        prev = make_prev_skill(version="1")
        repo = make_repo(
            active_skill=active, traces=traces, current_rate=0.70, prev_skill=prev
        )
        redis = make_redis(rollback_count=3)  # triggers circuit breaker

        guard = EvolutionGuard(
            repo=repo, redis=redis, rollback_threshold=0.10, max_rollbacks_per_day=3
        )
        await guard.check("chat-agent", "chat-skill")

        redis.incr.assert_awaited_once_with("evolution:rollback_count:chat-agent")
        redis.set.assert_awaited_once_with("evolution:paused:chat-agent", "true")
