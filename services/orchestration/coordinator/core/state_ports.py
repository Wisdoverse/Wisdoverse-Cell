"""Ports for Coordinator runtime state persistence."""

from typing import Any, Protocol

from .domain.state_records import (
    CoordinatorAgentStateRecord,
    CoordinatorDecisionRecord,
)


class CoordinatorStateStorePort(Protocol):
    """Runtime state operations required by the Coordinator service."""

    async def get_agent_states(self) -> dict[str, CoordinatorAgentStateRecord]:
        """Return current agent state records."""

    async def update_agent_state(
        self,
        agent_id: str,
        *,
        status: str = "idle",
        current_task: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update one agent state record."""

    async def get_pending_decisions(self) -> list[CoordinatorDecisionRecord]:
        """Return pending coordinator decisions."""

    async def persist(self, decisions: list[Any]) -> None:
        """Persist newly produced coordinator decisions."""

    async def get_workflow_states(self) -> dict[str, Any]:
        """Return current workflow state records."""

    async def upsert_workflow_state(self, state: Any) -> None:
        """Validate and persist one workflow state record."""
