"""SQLAlchemy adapter for Evolution trace analysis reads."""

from shared.evolution.db.database import EvolutionDatabaseManager
from shared.evolution.db.repository import EvolutionRepository

from ..core.analysis_ports import (
    AgentPerformanceSnapshot,
    EvolutionTraceAnalysisStore,
)


class SqlAlchemyEvolutionTraceAnalysisStore(EvolutionTraceAnalysisStore):
    """SQLAlchemy-backed read model for global evolution analysis."""

    def __init__(self, db_manager: EvolutionDatabaseManager):
        self._db_manager = db_manager

    async def list_agent_performance(
        self,
        agent_ids: list[str],
        *,
        limit_per_agent: int = 100,
    ) -> list[AgentPerformanceSnapshot]:
        async with self._db_manager.session() as session:
            repo = EvolutionRepository(session)
            snapshots: list[AgentPerformanceSnapshot] = []
            for agent_id in agent_ids:
                traces = await repo.get_recent_traces(
                    agent_id,
                    limit=limit_per_agent,
                )
                if not traces:
                    continue
                success_count = sum(1 for trace in traces if trace.success)
                total_count = len(traces)
                snapshots.append(
                    AgentPerformanceSnapshot(
                        agent_id=agent_id,
                        success_count=success_count,
                        total_count=total_count,
                        success_rate=round(success_count / total_count, 4),
                    )
                )
            return snapshots
