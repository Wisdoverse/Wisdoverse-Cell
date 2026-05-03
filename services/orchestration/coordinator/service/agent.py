"""CoordinatorAgent - system orchestration worker."""
import asyncio
from typing import Any

from shared.infra.llm_gateway import llm_gateway
from shared.infra.scratchpad import Scratchpad
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.classifier import ClassifiedEvent, classify_event
from ..core.dispatcher import decision_to_event
from ..core.models import Decision
from ..core.think import think as think_fn
from ..db.state_store import CoordinatorStateStore

logger = get_logger("coordinator.agent")


class CoordinatorAgent(BaseAgent):
    """Global orchestration engine."""

    def __init__(self):
        super().__init__(
            agent_id="coordinator",
            agent_name="Coordinator",
            subscribed_events=[
                EventTypes.COORDINATOR_COMMAND,
                EventTypes.TASK_NOTIFICATION,
                EventTypes.TASK_PROGRESS,
                EventTypes.PM_PRD_READY,
                EventTypes.PM_DECOMPOSE_COMPLETED,
                EventTypes.PM_DECOMPOSITION_FAILED,
                EventTypes.ANALYSIS_RISK_DETECTED,
            ],
            published_events=[
                EventTypes.COORDINATOR_RESPONSE,
                EventTypes.COORDINATOR_DISPATCH,
                EventTypes.PM_TASKS_READY_FOR_DEV,
                EventTypes.QA_RUN_REQUESTED,
            ],
        )
        self._scratchpad = Scratchpad()
        self._state_store = CoordinatorStateStore()
        self._llm = llm_gateway

    async def startup(self) -> None:
        await self._scratchpad.initialize()
        logger.info("coordinator_started")

    async def shutdown(self) -> None:
        logger.info("coordinator_stopped")

    async def handle_event(self, event: Event) -> list[Event]:
        """Single entry point for all events."""
        classified = classify_event(event)

        # Progress events update state directly, no LLM call
        if classified.kind == "progress":
            progress = classified.data
            await self._state_store.update_agent_state(
                progress.agent_id,
                status="working",
                current_task=progress.task_id,
            )
            return []

        # All other events go through synthesis
        scratchpad = await self._scratchpad.read_incremental()
        agent_states = await self._state_store.get_agent_states()
        pending = await self._state_store.get_pending_decisions()

        context = self._build_context(
            scratchpad=scratchpad,
            agent_states=agent_states,
            incoming=classified,
            pending_decisions=pending,
        )
        decisions = await self._think(context)

        outgoing = [decision_to_event(d) for d in decisions]

        await self._scratchpad.update(decisions)
        await self._state_store.persist(decisions)

        if self._scratchpad.should_compact():
            asyncio.create_task(self._scratchpad.compact())

        return outgoing

    async def handle_request(self, request: dict) -> dict:
        """Handle governance API requests."""
        result = await self.handle_standard_request(request)
        if result is not None:
            return result
        return {"error": "unknown action", "action": request.get("action")}

    def _build_context(
        self,
        *,
        scratchpad: str,
        agent_states: dict,
        incoming: ClassifiedEvent,
        pending_decisions: list,
    ) -> dict[str, Any]:
        """Build context dict for LLM synthesis."""
        return {
            "scratchpad": scratchpad,
            "agent_states": {
                k: v.model_dump() for k, v in agent_states.items()
            },
            "incoming_event": {
                "kind": incoming.kind,
                "data": (
                    incoming.data.model_dump()
                    if hasattr(incoming.data, "model_dump")
                    else incoming.data.payload
                ),
            },
            "pending_decisions": [d.model_dump() for d in pending_decisions],
        }

    async def _think(self, context: dict[str, Any]) -> list[Decision]:
        """LLM synthesis — calls think engine with current LLM gateway."""
        return await think_fn(context, llm=self._llm)
