"""
EvolvedAgent — composition wrapper that adds execution tracing to any BaseAgent.

Inherits from BaseAgent so ``isinstance(agent, BaseAgent)`` holds.
Delegates all business logic to the wrapped agent; adds trace collection
around ``handle_event`` calls.
"""

import asyncio
from random import random
from typing import TYPE_CHECKING, Any, Optional

from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .config import evolution_settings
from .trace_collector import TraceCollector, TraceHandle

if TYPE_CHECKING:
    from shared.evolution.canary_router import CanaryRouter
    from shared.evolution.db.database import EvolutionDatabaseManager
    from shared.evolution.evaluator import Evaluator
    from shared.evolution.kill_switch import KillSwitch
    from shared.evolution.skill_optimizer import SkillOptimizer
    from shared.protocols.a2a.models import AgentCard, Message

logger = get_logger("evolution.agent")


class EvolvedAgent(BaseAgent):
    """Wrapper that adds execution tracing to a BaseAgent.

    Usage::

        evolved = EvolvedAgent(my_agent, kill_switch=ks, db_manager=db)
        # Use evolved anywhere you'd use my_agent
    """

    def __init__(
        self,
        agent: BaseAgent,
        kill_switch: Optional["KillSwitch"] = None,
        db_manager: Optional["EvolutionDatabaseManager"] = None,
        evaluator: Optional["Evaluator"] = None,
        canary_router: Optional["CanaryRouter"] = None,
        skill_optimizer: Optional["SkillOptimizer"] = None,
    ):
        super().__init__(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            subscribed_events=agent.subscribed_events,
            published_events=agent.published_events,
            a2a_enabled=agent.a2a_enabled,
            mcp_enabled=agent.mcp_enabled,
        )
        self._agent = agent
        self._kill_switch = kill_switch
        self._db_manager = db_manager
        self._evaluator = evaluator
        self._canary_router = canary_router
        self._skill_optimizer = skill_optimizer
        self._trace_collector = TraceCollector(agent.agent_id)
        self._background_tasks: set[asyncio.Task[None]] = set()

    # ── Core event handling with tracing ──────────────────────────────────

    async def handle_event(self, event: Event) -> list[Event]:
        # If kill switch exists and evolution is disabled → pass through
        if self._kill_switch is not None:
            if not await self._kill_switch.is_enabled():
                return await self._agent.handle_event(event)

        # Sampling: skip tracing for a fraction of events
        if random() > evolution_settings.trace_sampling_rate:
            return await self._agent.handle_event(event)

        # Start trace
        trace = self._trace_collector.start(event)
        try:
            results = await self._agent.handle_event(event)
            trace.record_success(results)
            return results
        except Exception as exc:
            trace.record_failure(exc)
            raise
        finally:
            # Fire-and-forget: persist trace + Phase 2 hooks in background
            task = asyncio.create_task(self._post_execution(trace))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    # ── Post-execution hooks ─────────────────────────────────────────────

    async def _post_execution(self, trace: TraceHandle) -> None:
        """Post-execution hooks: persist, score, record canary, optimize."""
        # 1. Persist trace (existing logic)
        await self._persist_trace(trace)

        # 2. Score trace via evaluator (if configured)
        if self._evaluator and evolution_settings.auto_optimize:
            try:
                score = await self._evaluator.score_trace(trace)
                trace.auto_score = score
            except Exception as e:
                logger.warning("evaluator_scoring_failed", error=str(e))

        # 3. Record canary result (if experiment active)
        if self._canary_router and evolution_settings.canary_enabled:
            try:
                await self._canary_router.record_result(
                    self.agent_id,
                    trace.skill_used or "",
                    trace.trace_id,
                    trace.auto_score or (1.0 if trace.success else 0.0),
                )
            except Exception as e:
                logger.warning("canary_record_failed", error=str(e))

        # 4. Trigger optimization check (if configured)
        if self._skill_optimizer and evolution_settings.auto_optimize:
            try:
                self._skill_optimizer.increment_execution(
                    self.agent_id, trace.skill_used or ""
                )
                await self._skill_optimizer.maybe_optimize(
                    self.agent_id, trace.skill_used or ""
                )
            except Exception as e:
                logger.warning("auto_optimize_failed", error=str(e))

    # ── Background trace persistence ──────────────────────────────────────

    async def _persist_trace(self, trace: TraceHandle) -> None:
        """Persist a trace to the database. Failures are logged but never crash."""
        if self._db_manager is None:
            return
        try:
            async with self._db_manager.session() as session:
                from shared.evolution.db.repository import EvolutionRepository

                repo = EvolutionRepository(session)
                data = trace.to_dict()
                await repo.save_trace(
                    trace_id=data["trace_id"],
                    agent_id=data["agent_id"],
                    event_type=data["event_type"],
                    input_event=data["input_event"],
                    output_events=data["output_events"],
                    started_at=trace.started_at,
                    completed_at=trace.completed_at,
                    success=data["success"] or False,
                    llm_calls=data["llm_calls"],
                    skill_used=data["skill_used"],
                    skill_version=data["skill_version"],
                    error=data["error"],
                )
        except Exception as exc:
            logger.warning(
                "trace_persist_failed",
                agent_id=self.agent_id,
                error=str(exc),
            )

    def set_kill_switch(self, kill_switch: "KillSwitch") -> None:
        """Set or replace the kill switch at runtime (e.g. after Redis is available)."""
        self._kill_switch = kill_switch

    # ── Delegated methods ─────────────────────────────────────────────────

    async def handle_request(self, request: dict) -> dict:
        return await self._agent.handle_request(request)

    async def startup(self) -> None:
        await self._agent.startup()

    async def shutdown(self) -> None:
        await self._agent.shutdown()

    def get_agent_card(self) -> "AgentCard":
        return self._agent.get_agent_card()

    def get_a2a_skills(self) -> list[dict[str, Any]]:
        return self._agent.get_a2a_skills()

    async def handle_a2a_task(
        self, task_id: str, message: "Message"
    ) -> dict[str, Any]:
        return await self._agent.handle_a2a_task(task_id, message)

    def get_mcp_router(self) -> Any:
        return self._agent.get_mcp_router()

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        return self._agent.get_mcp_tools()

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the wrapped agent for methods not explicitly delegated."""
        return getattr(self._agent, name)

    def __repr__(self) -> str:
        return f"<EvolvedAgent wrapping {self._agent!r}>"
