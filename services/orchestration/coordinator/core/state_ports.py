"""Ports for Coordinator runtime state persistence."""

from typing import Any, Protocol


class CoordinatorStateStorePort(Protocol):
    """Runtime state operations required by the Coordinator service."""

    async def get_agent_states(self) -> dict[str, Any]:
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

    async def get_pending_decisions(self) -> list[Any]:
        """Return pending coordinator decisions."""

    async def persist(self, decisions: list[Any]) -> None:
        """Persist newly produced coordinator decisions."""
