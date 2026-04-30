"""
Evolution Kill Switch — Redis-backed global on/off for the evolution system.

Fail-safe: if Redis is unreachable, evolution is DISABLED to prevent runaway
self-modification when infrastructure is degraded.
"""

from shared.utils.logger import get_logger

_REDIS_KEY = "evolution:enabled"

logger = get_logger("evolution.kill_switch")


class KillSwitch:
    """Global kill switch for the self-evolution system.

    Reads/writes a single Redis key ``evolution:enabled``.
    - Missing key  → enabled (default ON)
    - "true"       → enabled
    - "false"      → disabled
    - Redis error  → disabled (fail-safe)
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    async def is_enabled(self) -> bool:
        """Return True if evolution is active, False to suppress all evolution logic.

        Returns False (fail-safe) if Redis is unreachable.
        """
        try:
            value = await self._redis.get(_REDIS_KEY)
        except Exception as exc:
            logger.warning(
                "kill_switch.redis_error",
                error=str(exc),
                action="disabling_evolution_fail_safe",
            )
            return False

        if value is None:
            # Key absent → default enabled
            return True

        # Normalise bytes or str
        if isinstance(value, bytes):
            value = value.decode()

        return value.lower() != "false"

    async def disable(self, reason: str = "") -> None:
        """Disable the evolution system globally.

        Args:
            reason: Human-readable explanation stored in logs only (not in Redis).
        """
        await self._redis.set(_REDIS_KEY, "false")
        logger.warning(
            "kill_switch.disabled",
            reason=reason or "no reason provided",
        )

    async def enable(self) -> None:
        """Re-enable the evolution system globally."""
        await self._redis.set(_REDIS_KEY, "true")
        logger.info("kill_switch.enabled")
