"""
CollaborationOrchestrator — routes events to matching collaboration patterns.

For active patterns: executes step chain in production (real side effects).
For shadow patterns: runs in background via ShadowRunner (no side effects).
"""

import asyncio

from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .models import CollaborationPattern, CollaborationStep, PatternStatus

logger = get_logger("evolution.orchestrator")


class CollaborationOrchestrator:
    """Routes events to matching collaboration patterns.

    For active patterns: executes step chain in production (real side effects).
    For shadow patterns: runs in background via ShadowRunner (no side effects).
    """

    def __init__(
        self,
        pattern_store,
        condition_evaluator,
        shadow_runner,
        agent_registry: dict[str, BaseAgent],
    ):
        self._store = pattern_store
        self._condition = condition_evaluator
        self._shadow_runner = shadow_runner
        self._agents = agent_registry
        self._background_tasks: set[asyncio.Task] = set()

    async def on_event(self, event: Event) -> list[Event]:
        """Process event through matching patterns.

        Returns output events from active patterns only.
        Shadow patterns are dispatched as fire-and-forget background tasks.
        """
        all_results: list[Event] = []

        # 1. Active patterns (production execution)
        active_patterns = await self._store.find_matching(
            event.event_type, PatternStatus.ACTIVE.value
        )
        for pattern in active_patterns:
            if self._condition.evaluate(
                pattern.trigger_condition, {"payload": event.payload}
            ):
                try:
                    results = await self._execute_pattern(pattern, event)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(
                        "pattern_execution_failed",
                        pattern_id=pattern.pattern_id,
                        error=str(e),
                    )

        # 2. Shadow patterns (background, fire-and-forget)
        shadow_patterns = await self._store.find_matching(
            event.event_type, PatternStatus.SHADOW.value
        )
        for pattern in shadow_patterns:
            if self._condition.evaluate(
                pattern.trigger_condition, {"payload": event.payload}
            ):
                task = asyncio.create_task(
                    self._run_and_store_shadow(pattern, event)
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

        return all_results

    async def _execute_pattern(self, pattern, event: Event) -> list[Event]:
        """Execute pattern steps sequentially using real agents."""
        all_output: list[Event] = []
        current_input = event

        for step in pattern.steps:
            # steps may be raw dicts (ORM row) or CollaborationStep instances
            if isinstance(step, dict):
                step = CollaborationStep(**step)

            agent = self._agents.get(step.agent_id)
            if agent is None:
                logger.warning(
                    "agent_not_found",
                    step_id=step.step_id,
                    agent_id=step.agent_id,
                )
                if step.on_failure == "abort":
                    break
                continue

            try:
                output = await asyncio.wait_for(
                    agent.handle_event(current_input),
                    timeout=step.timeout_seconds,
                )
                all_output.extend(output)
                if output and step.output_to:
                    current_input = output[0]
            except asyncio.TimeoutError:
                logger.warning(
                    "step_timeout",
                    step_id=step.step_id,
                    agent_id=step.agent_id,
                )
                if step.on_failure == "abort":
                    break
            except Exception as e:
                logger.error(
                    "step_failed",
                    step_id=step.step_id,
                    error=str(e),
                )
                if step.on_failure == "abort":
                    break

        return all_output

    async def _run_and_store_shadow(self, pattern, event: Event) -> None:
        """Convert ORM row to CollaborationPattern if needed, run shadow, store result."""
        try:
            if not isinstance(pattern, CollaborationPattern):
                p = CollaborationPattern(
                    pattern_id=pattern.pattern_id,
                    name=pattern.name,
                    status=pattern.status,
                    trigger_event=pattern.trigger_event,
                    trigger_condition=pattern.trigger_condition,
                    steps=[
                        CollaborationStep(**s) for s in (pattern.steps or [])
                    ],
                )
            else:
                p = pattern

            result = await self._shadow_runner.run_shadow(p, event)
            await self._store.add_shadow_result(
                pattern.pattern_id, result.model_dump(mode="json")
            )
        except Exception as e:
            logger.error(
                "shadow_run_failed",
                pattern_id=pattern.pattern_id,
                error=str(e),
            )
