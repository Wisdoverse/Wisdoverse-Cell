"""In-memory state store for Coordinator Agent.

First version uses in-memory dicts. PostgreSQL persistence
will be added in a later task.
"""
from datetime import UTC, datetime

from .models import AgentStateRecord, DecisionRecord, WorkflowState


class CoordinatorStateStore:
    """Manages Coordinator's runtime state."""

    def __init__(self):
        self._agent_states: dict[str, AgentStateRecord] = {}
        self._workflows: dict[str, WorkflowState] = {}
        self._pending_decisions: list[DecisionRecord] = []

    async def get_agent_states(self) -> dict[str, AgentStateRecord]:
        return dict(self._agent_states)

    async def update_agent_state(
        self,
        agent_id: str,
        *,
        status: str = "idle",
        current_task: str | None = None,
        error: str | None = None,
    ) -> None:
        self._agent_states[agent_id] = AgentStateRecord(
            agent_id=agent_id,
            status=status,
            current_task=current_task,
            last_output_at=datetime.now(UTC),
            error=error,
        )

    async def get_pending_decisions(self) -> list[DecisionRecord]:
        return list(self._pending_decisions)

    async def persist(self, decisions: list) -> None:
        """Persist decisions. In-memory for now."""
        pass
