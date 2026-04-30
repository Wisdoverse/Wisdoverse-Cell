"""DenialTracker -- remembers user-rejected actions to avoid re-proposing.

Redis key: denial:{agent_id}:{user_id}:{action_type}:{table_hash}
Value: JSON with reason + timestamps
TTL: configurable (default 3600s)
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from prometheus_client import Counter

from shared.utils.logger import get_logger

logger = get_logger("denial_tracker")

DENIAL_BLOCKED_TOTAL = Counter(
    "projectcell_denial_tracker_blocked_total",
    "Total times a tool call was blocked by denial cache",
    ["agent_id", "action_type"],
)


class DenialTracker:
    """Tracks user-rejected actions in Redis to prevent re-proposing."""

    def __init__(self, redis, ttl: int = 3600) -> None:  # noqa: ANN001
        self._redis = redis
        self._ttl = ttl

    @staticmethod
    def _key(agent_id: str, user_id: str, action_type: str, table_id: str) -> str:
        """Build Redis key with md5(table_id)[:12] for compactness."""
        table_hash = hashlib.md5(table_id.encode()).hexdigest()[:12]  # noqa: S324
        return f"denial:{agent_id}:{user_id}:{action_type}:{table_hash}"

    async def record_denial(
        self,
        agent_id: str,
        user_id: str,
        action_type: str,
        table_id: str,
        reason: str,
    ) -> None:
        """Store a denial record with TTL."""
        key = self._key(agent_id, user_id, action_type, table_id)
        value = json.dumps({
            "reason": reason,
            "recorded_at": datetime.now(UTC).isoformat(),
            "agent_id": agent_id,
            "user_id": user_id,
            "action_type": action_type,
            "table_id": table_id,
        })
        await self._redis.set(key, value, ex=self._ttl)
        logger.info(
            "denial_recorded",
            agent_id=agent_id,
            user_id=user_id,
            action_type=action_type,
        )

    async def is_denied(
        self,
        agent_id: str,
        user_id: str,
        action_type: str,
        table_id: str,
    ) -> dict | None:
        """Check if action was denied. Returns parsed dict on hit, None on miss."""
        key = self._key(agent_id, user_id, action_type, table_id)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        DENIAL_BLOCKED_TOTAL.labels(agent_id=agent_id, action_type=action_type).inc()
        logger.debug(
            "denial_cache_hit",
            agent_id=agent_id,
            user_id=user_id,
            action_type=action_type,
        )
        return data

    async def clear_denials(self, agent_id: str, user_id: str | None = None) -> int:
        """Delete denials by pattern. Returns number of keys deleted."""
        if user_id:
            pattern = f"denial:{agent_id}:{user_id}:*"
        else:
            pattern = f"denial:{agent_id}:*"

        count = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
                count += len(keys)
            if cursor == 0:
                break

        logger.info("denials_cleared", agent_id=agent_id, user_id=user_id, count=count)
        return count
