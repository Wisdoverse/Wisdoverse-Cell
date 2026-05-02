"""
AgentLoopCircuitBreaker - agent-loop circuit breaker.

Detects long-running agent loops with no progress or repeated errors and opens
automatically. Complements the service-call CircuitBreaker to protect agent task
loops.

State machine:
    CLOSED -> no_progress >= half_open_threshold -> HALF_OPEN
    CLOSED -> no_progress >= no_progress_threshold OR same_error >= same_error_threshold -> OPEN
    HALF_OPEN -> progress -> CLOSED
    HALF_OPEN -> no_progress >= no_progress_threshold -> OPEN
    OPEN -> manual reset only -> CLOSED
"""
import json
from datetime import UTC, datetime
from typing import Optional

from shared.infra.circuit_breaker import CircuitState
from shared.infra.metrics import (
    LOOP_BREAKER_NO_PROGRESS_ROUNDS,
    LOOP_BREAKER_OUTPUT_DECLINE_RATIO,
    LOOP_BREAKER_STATE,
    LOOP_BREAKER_TRIPS_TOTAL,
)
from shared.utils.logger import get_logger

logger = get_logger("agent_loop_breaker")

_KEY_PREFIX = "loop_breaker"


class AgentLoopBreakerError(Exception):
    def __init__(self, agent_id: str):
        super().__init__(f"Agent loop breaker is open for {agent_id}")
        self.agent_id = agent_id


class AgentLoopCircuitBreaker:
    def __init__(
        self,
        agent_id: str,
        no_progress_threshold: int = 3,
        same_error_threshold: int = 5,
        half_open_threshold: int = 2,
        output_decline_threshold: float = 0.3,
        output_decline_rounds: int = 3,
        redis=None,
    ):
        self.agent_id = agent_id
        self.no_progress_threshold = no_progress_threshold
        self.same_error_threshold = same_error_threshold
        self.half_open_threshold = half_open_threshold
        self.output_decline_threshold = output_decline_threshold
        self.output_decline_rounds = output_decline_rounds
        self._redis = redis
        self._key = f"{_KEY_PREFIX}:{agent_id}"
        self._history_key = f"{_KEY_PREFIX}:{agent_id}:history"
        self._output_lengths_key = f"{_KEY_PREFIX}:{agent_id}:output_lengths"

    @staticmethod
    def _decode(val) -> str:
        """Handle both bytes (decode_responses=False) and str (decode_responses=True)."""
        return val.decode() if isinstance(val, bytes) else str(val) if val is not None else ""

    async def _load(self) -> dict:
        raw = await self._redis.hgetall(self._key)
        if not raw:
            return {
                "state": CircuitState.CLOSED.value,
                "no_progress_count": 0,
                "same_error_count": 0,
                "last_error_signature": "",
                "total_opens": 0,
                "output_decline_count": 0,
            }
        # Support both bytes keys (decode_responses=False) and str keys (decode_responses=True)
        def _get(key: str, default: str = "") -> str:
            return self._decode(raw.get(key, raw.get(key.encode(), default)))

        return {
            "state": _get("state", "closed"),
            "no_progress_count": int(_get("no_progress_count", "0")),
            "same_error_count": int(_get("same_error_count", "0")),
            "last_error_signature": _get("last_error_signature", ""),
            "total_opens": int(_get("total_opens", "0")),
            "output_decline_count": int(_get("output_decline_count", "0")),
        }

    async def _save(self, data: dict) -> None:
        await self._redis.hset(self._key, mapping={
            "state": data["state"],
            "no_progress_count": str(data["no_progress_count"]),
            "same_error_count": str(data["same_error_count"]),
            "last_error_signature": data["last_error_signature"],
            "total_opens": str(data["total_opens"]),
            "output_decline_count": str(data["output_decline_count"]),
        })

    async def _record_transition(self, from_state: str, to_state: str, reason: str) -> None:
        entry = json.dumps({
            "timestamp": datetime.now(UTC).isoformat(),
            "from": from_state,
            "to": to_state,
            "reason": reason,
        })
        await self._redis.rpush(self._history_key, entry)
        await self._redis.ltrim(self._history_key, -50, -1)

    async def can_execute(self) -> bool:
        data = await self._load()
        return data["state"] != CircuitState.OPEN.value

    async def _check_output_decline(self, output_length: int) -> Optional[float]:
        """Track output length and detect declining output.

        RPUSHes to output_lengths list (capped at 10), then computes
        ratio = latest / mean(previous).  Returns the ratio when >= 3
        data points are available, else None.
        """
        await self._redis.rpush(self._output_lengths_key, str(output_length))
        await self._redis.ltrim(self._output_lengths_key, -10, -1)

        raw_lengths = await self._redis.lrange(self._output_lengths_key, 0, -1)
        lengths = [int(self._decode(v)) for v in raw_lengths]

        if len(lengths) < 3:
            return None

        previous = lengths[:-1]
        latest = lengths[-1]
        mean_previous = sum(previous) / len(previous)

        if mean_previous == 0:
            return None

        ratio = latest / mean_previous
        LOOP_BREAKER_OUTPUT_DECLINE_RATIO.labels(agent_id=self.agent_id).set(ratio)
        return ratio

    async def record_round(
        self,
        has_progress: bool,
        error_signature: Optional[str] = None,
        output_length: Optional[int] = None,
    ) -> None:
        data = await self._load()
        old_state = data["state"]

        # Track error signature
        if error_signature:
            if error_signature == data["last_error_signature"]:
                data["same_error_count"] += 1
            else:
                data["same_error_count"] = 1
                data["last_error_signature"] = error_signature
        else:
            data["same_error_count"] = 0
            data["last_error_signature"] = ""

        # Track progress
        if has_progress:
            data["no_progress_count"] = 0
        else:
            data["no_progress_count"] += 1

        # Track output decline
        if output_length is not None:
            ratio = await self._check_output_decline(output_length)
            if ratio is not None and ratio < self.output_decline_threshold:
                data["output_decline_count"] += 1
            elif ratio is not None:
                data["output_decline_count"] = 0
        # When output_length is None, decline detection is silently skipped

        # State transitions
        new_state = old_state

        # Same-error threshold overrides everything (even with progress)
        if data["same_error_count"] >= self.same_error_threshold:
            new_state = CircuitState.OPEN.value
        elif data["output_decline_count"] >= self.output_decline_rounds:
            new_state = CircuitState.OPEN.value
        elif old_state == CircuitState.CLOSED.value:
            if data["no_progress_count"] >= self.no_progress_threshold:
                new_state = CircuitState.OPEN.value
            elif data["no_progress_count"] >= self.half_open_threshold:
                new_state = CircuitState.HALF_OPEN.value
        elif old_state == CircuitState.HALF_OPEN.value:
            if has_progress and data["same_error_count"] < self.same_error_threshold:
                new_state = CircuitState.CLOSED.value
                data["no_progress_count"] = 0
            elif data["no_progress_count"] >= self.no_progress_threshold:
                new_state = CircuitState.OPEN.value

        if new_state == CircuitState.OPEN.value and old_state != CircuitState.OPEN.value:
            data["total_opens"] += 1

        data["state"] = new_state
        await self._save(data)
        self._emit_metrics(data, tripped=(new_state == CircuitState.OPEN.value and old_state != CircuitState.OPEN.value))

        if new_state != old_state:
            reason = (
                f"same_error({data['same_error_count']})"
                if data["same_error_count"] >= self.same_error_threshold
                else f"output_decline({data['output_decline_count']})"
                if data["output_decline_count"] >= self.output_decline_rounds
                else f"no_progress({data['no_progress_count']})"
                if not has_progress
                else "progress_recovered"
            )
            await self._record_transition(old_state, new_state, reason)
            logger.info(
                "loop_breaker_transition",
                agent_id=self.agent_id,
                from_state=old_state,
                to_state=new_state,
                reason=reason,
            )

    _STATE_VALUES = {
        CircuitState.CLOSED.value: 0,
        CircuitState.HALF_OPEN.value: 1,
        CircuitState.OPEN.value: 2,
    }

    def _emit_metrics(self, data: dict, *, tripped: bool = False) -> None:
        LOOP_BREAKER_STATE.labels(agent_id=self.agent_id).set(
            self._STATE_VALUES.get(data["state"], 0)
        )
        LOOP_BREAKER_NO_PROGRESS_ROUNDS.labels(agent_id=self.agent_id).set(
            data["no_progress_count"]
        )
        if tripped:
            if data["same_error_count"] >= self.same_error_threshold:
                reason = "same_error"
            elif data["output_decline_count"] >= self.output_decline_rounds:
                reason = "output_decline"
            else:
                reason = "no_progress"
            LOOP_BREAKER_TRIPS_TOTAL.labels(agent_id=self.agent_id, reason=reason).inc()

    async def reset(self, reason: str = "manual") -> None:
        data = await self._load()
        old_state = data["state"]
        new_data = {
            "state": CircuitState.CLOSED.value,
            "no_progress_count": 0,
            "same_error_count": 0,
            "last_error_signature": "",
            "total_opens": data["total_opens"],
            "output_decline_count": 0,
        }
        await self._save(new_data)
        await self._redis.delete(self._output_lengths_key)
        self._emit_metrics(new_data)
        if old_state != CircuitState.CLOSED.value:
            await self._record_transition(old_state, CircuitState.CLOSED.value, f"reset:{reason}")
            logger.info(
                "loop_breaker_reset",
                agent_id=self.agent_id,
                from_state=old_state,
                reason=reason,
            )

    async def get_state(self) -> dict:
        data = await self._load()
        data["agent_id"] = self.agent_id
        return data
