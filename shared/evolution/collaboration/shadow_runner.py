"""
ShadowRunner — executes collaboration patterns in shadow mode.

Shadow mode means read-only, no side effects: agents run against real events
but their outputs are captured for analysis rather than propagated to the
production event bus.

A semaphore caps concurrent shadow runs to prevent resource exhaustion.
Each run gets its own ShadowEventBus and uses per-agent locks to prevent
concurrent bus-swap races on shared agent instances.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .models import CollaborationPattern, ShadowRunResult
from .shadow_event_bus import ShadowEventBus

logger = get_logger("evolution.shadow")


class ShadowRunner:
    """Executes collaboration patterns in shadow mode (read-only, no side effects).

    Each run gets its own ShadowEventBus to avoid cross-run pollution.
    Per-agent asyncio locks prevent concurrent runs from racing on bus swap.
    """

    MAX_CONCURRENT_SHADOWS = 3

    def __init__(self, agent_registry: dict[str, BaseAgent]):
        self._agents = agent_registry
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SHADOWS)
        self._agent_locks: dict[str, asyncio.Lock] = {}

    def _get_agent_lock(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self._agent_locks:
            self._agent_locks[agent_id] = asyncio.Lock()
        return self._agent_locks[agent_id]

    async def run_shadow(
        self, pattern: CollaborationPattern, trigger_event: Event,
    ) -> ShadowRunResult:
        """Run pattern in shadow mode. Acquires semaphore to limit concurrency."""
        async with self._semaphore:
            return await self._execute(pattern, trigger_event)

    async def _execute(
        self, pattern: CollaborationPattern, trigger_event: Event,
    ) -> ShadowRunResult:
        start = datetime.now(UTC)
        results: list[dict[str, Any]] = []
        current_input = trigger_event
        # Each run gets its own bus — no cross-run pollution
        shadow_bus = ShadowEventBus()

        for step in pattern.steps:
            agent = self._agents.get(step.agent_id)
            if agent is None:
                results.append({
                    "step_id": step.step_id,
                    "success": False,
                    "error": f"Agent {step.agent_id} not found",
                })
                if step.on_failure == "abort":
                    break
                continue

            # Per-agent lock prevents concurrent shadow runs from
            # racing on the same agent's _event_bus attribute
            lock = self._get_agent_lock(step.agent_id)
            should_abort = False
            async with lock:
                original_bus = getattr(agent, "_event_bus", None)
                if original_bus is not None:
                    agent._event_bus = shadow_bus
                try:
                    output = await asyncio.wait_for(
                        agent.handle_event(current_input),
                        timeout=step.timeout_seconds,
                    )
                    results.append({
                        "step_id": step.step_id,
                        "success": True,
                        "output_count": len(output),
                    })
                    if output and step.output_to:
                        current_input = output[0]
                except asyncio.TimeoutError:
                    logger.warning(
                        "shadow_step_timeout",
                        pattern_id=pattern.pattern_id,
                        step_id=step.step_id,
                        timeout=step.timeout_seconds,
                    )
                    results.append({
                        "step_id": step.step_id,
                        "success": False,
                        "error": "timeout",
                    })
                    should_abort = step.on_failure == "abort"
                except Exception as e:
                    logger.warning(
                        "shadow_step_error",
                        pattern_id=pattern.pattern_id,
                        step_id=step.step_id,
                        error=str(e),
                    )
                    results.append({
                        "step_id": step.step_id,
                        "success": False,
                        "error": str(e),
                    })
                    should_abort = step.on_failure == "abort"
                finally:
                    if original_bus is not None:
                        agent._event_bus = original_bus
            if should_abort:
                break

        end = datetime.now(UTC)
        duration_ms = int((end - start).total_seconds() * 1000)

        return ShadowRunResult(
            pattern_id=pattern.pattern_id,
            trigger_event_id=trigger_event.event_id,
            timestamp=start,
            steps=results,
            total_duration_ms=duration_ms,
        )
