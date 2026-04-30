"""
Evolution Guard — auto-rollback + circuit breaker for degraded skills.

The guard is called asynchronously after each handle_event in EvolvedAgent.
It compares the current success rate against the active skill's baseline and
rolls back to the previous version if degradation exceeds the threshold.

A Redis-backed circuit breaker prevents runaway rollbacks (max N per 24 h).
"""

from shared.utils.logger import get_logger

_ROLLBACK_COUNT_KEY = "evolution:rollback_count:{agent_id}"
_PAUSED_KEY = "evolution:paused:{agent_id}"
_TTL_24H = 86_400  # seconds

logger = get_logger("evolution.guard")


class EvolutionGuard:
    """Monitor skill performance and roll back degraded skills automatically.

    Args:
        repo: EvolutionRepository (or compatible mock) — data access layer.
        redis: Async Redis client for circuit-breaker counters.
        rollback_threshold: Minimum degradation (absolute, 0-1) that triggers a
            rollback.  Default 0.10 means a 10 percentage-point drop.
        min_samples: Minimum number of recent traces required before a rollback
            decision can be made.
        max_rollbacks_per_day: Circuit-breaker limit — once this many rollbacks
            have been performed for an agent within 24 h, further rollbacks are
            suspended and the agent is paused.
    """

    def __init__(
        self,
        repo,
        redis,
        rollback_threshold: float = 0.10,
        min_samples: int = 10,
        max_rollbacks_per_day: int = 3,
    ) -> None:
        self._repo = repo
        self._redis = redis
        self._rollback_threshold = rollback_threshold
        self._min_samples = min_samples
        self._max_rollbacks_per_day = max_rollbacks_per_day

    # ── Public API ────────────────────────────────────────────────────────

    async def check(self, agent_id: str, skill_id: str) -> bool:
        """Check whether the current active skill needs to be rolled back.

        Returns:
            True  — rollback was performed.
            False — no action taken (stable, insufficient data, or guard tripped).
        """
        # 1. Fetch active skill; abort if none or never promoted.
        active_skill = await self._repo.get_active_skill(skill_id)
        if active_skill is None or active_skill.promoted_at is None:
            return False

        # 2. Fetch recent traces; abort if fewer than min_samples.
        traces = await self._repo.get_recent_traces(
            agent_id, limit=self._min_samples, skill_id=skill_id
        )
        if len(traces) < self._min_samples:
            return False

        # 3. Calculate current success rate.
        current_rate = await self._repo.calc_success_rate(
            agent_id, skill_id=skill_id, limit=self._min_samples
        )

        # 4. Compare with baseline; no rollback if degradation is within threshold.
        baseline = active_skill.success_rate
        degradation = baseline - current_rate
        if degradation <= self._rollback_threshold:
            return False

        # 5. Circuit breaker: increment 24-h rollback counter for this agent.
        counter_key = _ROLLBACK_COUNT_KEY.format(agent_id=agent_id)
        new_count = await self._redis.incr(counter_key)
        await self._redis.expire(counter_key, _TTL_24H)

        if new_count > self._max_rollbacks_per_day:
            paused_key = _PAUSED_KEY.format(agent_id=agent_id)
            await self._redis.set(paused_key, "true")
            logger.warning(
                "evolution.guard.circuit_breaker_tripped",
                agent_id=agent_id,
                skill_id=skill_id,
                rollback_count=new_count,
                max_rollbacks_per_day=self._max_rollbacks_per_day,
            )
            return False

        # 6. Fetch previous active skill to roll back to.
        prev_skill = await self._repo.get_previous_active(skill_id)
        if prev_skill is None:
            logger.error(
                "evolution.guard.no_previous_skill",
                agent_id=agent_id,
                skill_id=skill_id,
                active_version=active_skill.version,
            )
            return False

        # 7. Promote previous version (rollback).
        await self._repo.promote_skill(skill_id, prev_skill.version)
        logger.warning(
            "evolution.guard.rollback_triggered",
            agent_id=agent_id,
            skill_id=skill_id,
            rolled_back_from=active_skill.version,
            rolled_back_to=prev_skill.version,
            baseline_rate=baseline,
            current_rate=current_rate,
            degradation=degradation,
            threshold=self._rollback_threshold,
        )
        return True
