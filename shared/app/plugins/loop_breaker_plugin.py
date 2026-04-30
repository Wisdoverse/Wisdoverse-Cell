"""AgentLoopBreakerPlugin — detects stuck agent loops and halts execution."""
import hashlib
from typing import Any

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.infra.agent_loop_breaker import AgentLoopBreakerError, AgentLoopCircuitBreaker
from shared.infra.circuit_breaker import CircuitState
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger("plugin.loop-breaker")


class _LoopBreakerAgentWrapper(BaseAgent):
    """Wraps an agent to feed round outcomes into the loop breaker."""

    def __init__(self, inner: BaseAgent, breaker: AgentLoopCircuitBreaker):
        super().__init__(
            agent_id=inner.agent_id,
            agent_name=inner.agent_name,
            subscribed_events=inner.subscribed_events,
            published_events=inner.published_events,
            a2a_enabled=inner.a2a_enabled,
            mcp_enabled=inner.mcp_enabled,
        )
        self._inner = inner
        self._breaker = breaker

    async def handle_event(self, event: Event) -> list[Event]:
        if not await self._breaker.can_execute():
            raise AgentLoopBreakerError(self.agent_id)

        try:
            result = await self._inner.handle_event(event)
            # Extract output_tokens from event result metadata if available,
            # otherwise fall back to payload size estimate.
            output_length = None
            if result:
                for evt in result:
                    meta = getattr(evt, "metadata", None) or {}
                    if isinstance(meta, dict) and "output_tokens" in meta:
                        output_length = int(meta["output_tokens"])
                        break
                    elif hasattr(meta, "model_dump"):
                        md = meta.model_dump()
                        if "output_tokens" in md:
                            output_length = int(md["output_tokens"])
                            break
                if output_length is None:
                    output_length = sum(len(str(e.payload)) for e in result)
            else:
                output_length = 0
            await self._breaker.record_round(
                has_progress=True, output_length=output_length
            )
            return result
        except AgentLoopBreakerError:
            raise
        except Exception as exc:
            sig = hashlib.md5(
                f"{type(exc).__name__}:{exc}".encode(), usedforsecurity=False
            ).hexdigest()[:16]
            await self._breaker.record_round(
                has_progress=False,
                error_signature=f"{type(exc).__name__}:{sig}",
                output_length=0,
            )
            raise

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        # Intercept reset_loop_breaker at the public API level
        result = await self.handle_standard_request(request)
        if result is not None:
            return result
        return await self._inner.handle_request(request)

    async def handle_standard_request(
        self, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        if request.get("action") == "reset_loop_breaker":
            reason = request.get("reason", "governance")
            await self._breaker.reset(reason=reason)
            state = await self._breaker.get_state()
            return {"status": "reset", "breaker_state": state}
        return await self._inner.handle_standard_request(request)

    async def startup(self) -> None:
        await self._inner.startup()

    async def shutdown(self) -> None:
        await self._inner.shutdown()

    async def health_check(self) -> dict[str, bool]:
        return await self._inner.health_check()


class AgentLoopBreakerPlugin(RuntimePlugin):
    """RuntimePlugin that wraps agents with loop-level circuit breaking."""

    name = "loop-breaker"

    def __init__(
        self,
        no_progress_threshold: int = 3,
        same_error_threshold: int = 5,
        half_open_threshold: int = 2,
        output_decline_threshold: float = 0.3,
        output_decline_rounds: int = 3,
        redis=None,
    ):
        self._no_progress_threshold = no_progress_threshold
        self._same_error_threshold = same_error_threshold
        self._half_open_threshold = half_open_threshold
        self._output_decline_threshold = output_decline_threshold
        self._output_decline_rounds = output_decline_rounds
        self._redis = redis
        self._breaker: AgentLoopCircuitBreaker | None = None

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        self._breaker = AgentLoopCircuitBreaker(
            agent_id=agent.agent_id,
            no_progress_threshold=self._no_progress_threshold,
            same_error_threshold=self._same_error_threshold,
            half_open_threshold=self._half_open_threshold,
            output_decline_threshold=self._output_decline_threshold,
            output_decline_rounds=self._output_decline_rounds,
            redis=self._redis,
        )
        return _LoopBreakerAgentWrapper(agent, self._breaker)

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if not self._breaker:
            return {}
        state = await self._breaker.get_state()
        s = state["state"]
        if s == CircuitState.OPEN.value:
            return {"loop_breaker": HealthCheckResult(status="down", detail="loop breaker open")}
        if s == CircuitState.HALF_OPEN.value:
            return {"loop_breaker": HealthCheckResult(status="degraded", detail="loop breaker half-open")}
        return {"loop_breaker": HealthCheckResult(status="ok", detail="")}
