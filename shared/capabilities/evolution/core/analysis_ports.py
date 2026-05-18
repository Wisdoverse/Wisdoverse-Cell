"""Ports for evolution capability trace analysis persistence."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AgentPerformanceSnapshot:
    """Recent execution performance for one runtime agent."""

    agent_id: str
    success_count: int
    total_count: int
    success_rate: float


class EvolutionTraceAnalysisStore(Protocol):
    """Read-side persistence port for global evolution analysis."""

    async def list_agent_performance(
        self,
        agent_ids: list[str],
        *,
        limit_per_agent: int = 100,
    ) -> list[AgentPerformanceSnapshot]:
        """Return recent performance snapshots for the requested agents."""
