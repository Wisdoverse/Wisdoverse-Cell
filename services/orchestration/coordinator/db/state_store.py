"""In-memory state store for Coordinator Agent.

First version uses in-memory dicts. PostgreSQL persistence
will be added in a later task.
"""
from datetime import UTC, datetime

from shared.core.ids import IDPrefix, generate_id

from ..core.domain.state_records import (
    CoordinatorAgentStateRecord,
    CoordinatorDecisionRecord,
)
from ..core.domain.workflow_state import CoordinatorWorkflowState
from .models import WorkflowState


class CoordinatorStateStore:
    """Manages Coordinator's runtime state."""

    def __init__(self):
        self._agent_states: dict[str, CoordinatorAgentStateRecord] = {}
        self._workflows: dict[str, WorkflowState] = {}
        self._pending_decisions: list[CoordinatorDecisionRecord] = []

    async def get_agent_states(self) -> dict[str, CoordinatorAgentStateRecord]:
        return dict(self._agent_states)

    async def update_agent_state(
        self,
        agent_id: str,
        *,
        status: str = "idle",
        current_task: str | None = None,
        error: str | None = None,
    ) -> None:
        state = CoordinatorAgentStateRecord.create(
            agent_id=agent_id,
            status=status,
            current_task=current_task,
            last_output_at=datetime.now(UTC),
            error=error,
        )
        self._agent_states[str(state.agent_id)] = state

    async def get_pending_decisions(self) -> list[CoordinatorDecisionRecord]:
        return list(self._pending_decisions)

    async def get_workflow_states(self) -> dict[str, WorkflowState]:
        return dict(self._workflows)

    async def upsert_workflow_state(self, state: WorkflowState) -> None:
        """Validate and store workflow state through the domain aggregate."""
        workflow = CoordinatorWorkflowState.from_record(state)
        self._workflows[workflow.workflow_id] = WorkflowState(
            **workflow.to_record_kwargs()
        )

    async def persist(self, decisions: list) -> None:
        """Persist coordinator decisions into the in-memory operator state."""
        for decision in decisions:
            record = CoordinatorDecisionRecord.create(
                decision_id=generate_id(IDPrefix.DECISION),
                workflow_id=decision.workflow_id,
                reasoning=decision.reasoning or "",
                action=decision.action,
                target_agent=decision.target_agent,
                task_id=decision.task_id,
            )
            self._pending_decisions.append(record)
            await self.update_agent_state(
                decision.target_agent,
                status="working",
                current_task=decision.task_id,
            )
        self._pending_decisions = self._pending_decisions[-100:]
