"""Application use cases for Coordinator event orchestration."""
from __future__ import annotations

import asyncio
from typing import Any, Protocol

from shared.schemas.event import Event

from .classifier import ClassifiedEvent, classify_event
from .dispatcher import decision_to_event
from .models import Decision
from .state_ports import CoordinatorStateStorePort
from .unit_of_work_ports import CoordinatorUnitOfWorkFactory


class CoordinatorScratchpadPort(Protocol):
    """Scratchpad operations required by Coordinator event handling."""

    async def read_incremental(self) -> str:
        """Read the incremental scratchpad context."""

    async def update(self, decisions: list[Decision]) -> None:
        """Append produced decisions to the scratchpad."""

    def should_compact(self) -> bool:
        """Return whether the scratchpad should be compacted."""

    async def compact(self) -> None:
        """Compact the scratchpad."""


class CoordinatorThinkerPort(Protocol):
    """Anti-Corruption Layer to the LLM-backed coordinator thinker.

    The thinker translates a coordination `context` (scratchpad +
    agent states + incoming event + pending decisions) into a typed
    list of `Decision` records. Implementations are responsible for
    classifying any LLM response into the domain shape; raw LLM output
    must not escape this port.

    Defined as a callable Protocol so that any function or callable
    object satisfying the signature can be used without inheritance.
    The port name makes the boundary explicit per
    `architecture-principles.md` §4.6 (External Calls) and
    `ddd-compliance-audit.md` row DDD-019.
    """

    async def __call__(self, context: dict[str, Any]) -> list[Decision]: ...


class CoordinatorEventUseCase:
    """Coordinate state, memory, and decision synthesis for inbound events."""

    def __init__(
        self,
        *,
        scratchpad: CoordinatorScratchpadPort,
        state_store: CoordinatorStateStorePort,
        thinker: CoordinatorThinkerPort,
        uow_factory: CoordinatorUnitOfWorkFactory | None = None,
    ):
        self._scratchpad = scratchpad
        self._state_store = state_store
        self._thinker = thinker
        self._uow_factory = uow_factory

    async def handle(self, event: Event) -> list[Event]:
        classified = classify_event(event)

        if classified.kind == "progress":
            progress = classified.data
            await self._update_agent_state_in_uow(
                progress.agent_id,
                status="working",
                current_task=progress.task_id,
            )
            return []

        scratchpad = await self._scratchpad.read_incremental()
        agent_states = await self._state_store.get_agent_states()
        pending = await self._state_store.get_pending_decisions()

        context = self._build_context(
            scratchpad=scratchpad,
            agent_states=agent_states,
            incoming=classified,
            pending_decisions=pending,
        )
        decisions = await self._thinker(context)
        trace_id = event.metadata.trace_id if event.metadata else None
        if trace_id:
            decisions = [
                decision
                if decision.trace_id
                else decision.model_copy(update={"trace_id": trace_id})
                for decision in decisions
            ]

        outgoing = [decision_to_event(decision) for decision in decisions]

        await self._scratchpad.update(decisions)
        await self._persist_decisions_in_uow(decisions)

        if self._scratchpad.should_compact():
            asyncio.create_task(self._scratchpad.compact())

        return outgoing

    async def _update_agent_state_in_uow(
        self,
        agent_id: str,
        *,
        status: str,
        current_task: str | None,
    ) -> None:
        """Apply one agent-state mutation, transactionally when a UoW is wired."""
        if self._uow_factory is None:
            await self._state_store.update_agent_state(
                agent_id,
                status=status,
                current_task=current_task,
            )
            return
        async with self._uow_factory() as uow:
            await uow.state_store.update_agent_state(
                agent_id,
                status=status,
                current_task=current_task,
            )
            await uow.commit()

    async def _persist_decisions_in_uow(self, decisions: list[Decision]) -> None:
        """Persist coordinator decisions, transactionally when a UoW is wired."""
        if self._uow_factory is None:
            await self._state_store.persist(decisions)
            return
        async with self._uow_factory() as uow:
            await uow.state_store.persist(decisions)
            await uow.commit()

    def _build_context(
        self,
        *,
        scratchpad: str,
        agent_states: dict[str, Any],
        incoming: ClassifiedEvent,
        pending_decisions: list[Any],
    ) -> dict[str, Any]:
        return {
            "scratchpad": scratchpad,
            "agent_states": {
                key: value.model_dump() for key, value in agent_states.items()
            },
            "incoming_event": {
                "kind": incoming.kind,
                "data": (
                    incoming.data.model_dump()
                    if hasattr(incoming.data, "model_dump")
                    else incoming.data.payload
                ),
            },
            "pending_decisions": [
                decision.model_dump() for decision in pending_decisions
            ],
        }
