"""
Evolution Repository — data access layer for evolution tables.

Accepts an ``AsyncSession`` (injected by DatabaseManager).
Uses ``flush()`` instead of ``commit()`` — the session context manager handles commits.
"""

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import (
    EvolutionExperiment,
    EvolutionMemory,
    EvolutionReflection,
    EvolutionSkillConfig,
    EvolutionTrace,
)


class EvolutionRepository:
    """Data access repository for evolution system tables."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Skill Config ───────────────────────────────────────────────────────

    async def save_skill_config(
        self,
        skill_id: str,
        version: str,
        status: str = "candidate",
        system_prompt: str = "",
        parameters: Optional[dict[str, Any]] = None,
        few_shot_examples: Optional[list[dict[str, Any]]] = None,
        output_format: str = "",
        target_model: str = "",
    ) -> EvolutionSkillConfig:
        """Create a new skill config row."""
        row = EvolutionSkillConfig(
            skill_id=skill_id,
            version=version,
            status=status,
            system_prompt=system_prompt,
            parameters=parameters or {},
            few_shot_examples=few_shot_examples or [],
            output_format=output_format,
            target_model=target_model,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_active_skill(self, skill_id: str) -> Optional[EvolutionSkillConfig]:
        """Return the currently active config for a skill, or None."""
        result = await self.session.execute(
            select(EvolutionSkillConfig)
            .where(EvolutionSkillConfig.skill_id == skill_id)
            .where(EvolutionSkillConfig.status == "active")
            .order_by(EvolutionSkillConfig.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_skill_by_version(
        self, skill_id: str, version: str
    ) -> Optional[EvolutionSkillConfig]:
        """Return a specific version of a skill config."""
        result = await self.session.execute(
            select(EvolutionSkillConfig)
            .where(EvolutionSkillConfig.skill_id == skill_id)
            .where(EvolutionSkillConfig.version == version)
        )
        return result.scalar_one_or_none()

    async def promote_skill(self, skill_id: str, version: str) -> None:
        """Promote a candidate to active, retiring the current active version."""
        # Retire current active
        await self.session.execute(
            update(EvolutionSkillConfig)
            .where(EvolutionSkillConfig.skill_id == skill_id)
            .where(EvolutionSkillConfig.status == "active")
            .values(status="retired")
        )
        # Promote candidate
        await self.session.execute(
            update(EvolutionSkillConfig)
            .where(EvolutionSkillConfig.skill_id == skill_id)
            .where(EvolutionSkillConfig.version == version)
            .values(status="active", promoted_at=datetime.now(UTC))
        )
        await self.session.flush()

    async def get_previous_active(
        self, skill_id: str
    ) -> Optional[EvolutionSkillConfig]:
        """Return the most recently retired config for a skill (for rollback)."""
        result = await self.session.execute(
            select(EvolutionSkillConfig)
            .where(EvolutionSkillConfig.skill_id == skill_id)
            .where(EvolutionSkillConfig.status == "retired")
            .order_by(EvolutionSkillConfig.promoted_at.desc().nulls_last())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Traces ─────────────────────────────────────────────────────────────

    async def save_trace(
        self,
        trace_id: str,
        agent_id: str,
        event_type: str,
        input_event: Optional[dict[str, Any]] = None,
        output_events: Optional[list[dict[str, Any]]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        success: bool = True,
        llm_calls: Optional[list[dict[str, Any]]] = None,
        skill_used: Optional[str] = None,
        skill_version: Optional[str] = None,
        error: Optional[str] = None,
        human_rating: Optional[int] = None,
        human_correction: Optional[str] = None,
        auto_score: Optional[float] = None,
    ) -> EvolutionTrace:
        """Create a new execution trace row."""
        row = EvolutionTrace(
            trace_id=trace_id,
            agent_id=agent_id,
            event_type=event_type,
            input_event=input_event,
            output_events=output_events or [],
            llm_calls=llm_calls or [],
            skill_used=skill_used,
            skill_version=skill_version,
            started_at=started_at or datetime.now(UTC),
            completed_at=completed_at,
            success=success,
            error=error,
            human_rating=human_rating,
            human_correction=human_correction,
            auto_score=auto_score,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_recent_traces(
        self,
        agent_id: str,
        limit: int = 50,
        skill_id: Optional[str] = None,
    ) -> list[EvolutionTrace]:
        """Return recent traces for an agent, optionally filtered by skill."""
        query = (
            select(EvolutionTrace)
            .where(EvolutionTrace.agent_id == agent_id)
            .order_by(EvolutionTrace.created_at.desc())
            .limit(limit)
        )
        if skill_id is not None:
            query = query.where(EvolutionTrace.skill_used == skill_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def calc_success_rate(
        self,
        agent_id: str,
        skill_id: Optional[str] = None,
        limit: int = 50,
    ) -> float:
        """Calculate success rate over the most recent traces."""
        traces = await self.get_recent_traces(agent_id, limit=limit, skill_id=skill_id)
        if not traces:
            return 0.0
        successes = sum(1 for t in traces if t.success)
        return successes / len(traces)

    # ── Reflections ────────────────────────────────────────────────────────

    async def save_reflection(
        self,
        agent_id: str,
        skill_id: str,
        success_patterns: Optional[list[str]] = None,
        failure_patterns: Optional[list[str]] = None,
        optimization_suggestions: Optional[list[str]] = None,
        human_corrections_summary: str = "",
    ) -> EvolutionReflection:
        """Create a new reflection row."""
        row = EvolutionReflection(
            agent_id=agent_id,
            skill_id=skill_id,
            success_patterns=success_patterns or [],
            failure_patterns=failure_patterns or [],
            optimization_suggestions=optimization_suggestions or [],
            human_corrections_summary=human_corrections_summary,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_recent_reflections(
        self, agent_id: str, skill_id: str, limit: int = 5
    ) -> list[EvolutionReflection]:
        """Get the N most recent reflections for an agent+skill pair."""
        stmt = (
            select(EvolutionReflection)
            .where(
                EvolutionReflection.agent_id == agent_id,
                EvolutionReflection.skill_id == skill_id,
            )
            .order_by(desc(EvolutionReflection.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Experiments ────────────────────────────────────────────────────────

    async def save_experiment(
        self,
        experiment_id: str,
        agent_id: str,
        skill_id: str,
        control_version: int,
        candidate_version: int,
        traffic_pct: int = 10,
        min_samples: int = 50,
        max_duration_hours: int = 72,
        success_metric: str = "success_rate",
        min_improvement: float = 0.05,
    ) -> EvolutionExperiment:
        """Create a new experiment row."""
        row = EvolutionExperiment(
            experiment_id=experiment_id,
            agent_id=agent_id,
            skill_id=skill_id,
            control_version=control_version,
            candidate_version=candidate_version,
            traffic_pct=traffic_pct,
            min_samples=min_samples,
            max_duration_hours=max_duration_hours,
            success_metric=success_metric,
            min_improvement=min_improvement,
            control_results=[],
            candidate_results=[],
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_active_experiment(
        self, agent_id: str, skill_id: str
    ) -> Optional[EvolutionExperiment]:
        """Return the running experiment for an agent+skill, or None."""
        result = await self.session.execute(
            select(EvolutionExperiment)
            .where(EvolutionExperiment.agent_id == agent_id)
            .where(EvolutionExperiment.skill_id == skill_id)
            .where(EvolutionExperiment.status == "running")
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def conclude_experiment(
        self,
        experiment_id: str,
        status: str,
        concluded_at: Optional[datetime] = None,
    ) -> None:
        """Mark an experiment as concluded or rolled back."""
        await self.session.execute(
            update(EvolutionExperiment)
            .where(EvolutionExperiment.experiment_id == experiment_id)
            .values(
                status=status,
                concluded_at=concluded_at or datetime.now(UTC),
            )
        )
        await self.session.flush()

    async def add_experiment_result(
        self,
        experiment_id: str,
        is_candidate: bool,
        score: float,
    ) -> None:
        """Append a score to control_results or candidate_results JSON array."""
        row = await self.session.execute(
            select(EvolutionExperiment).where(
                EvolutionExperiment.experiment_id == experiment_id
            )
        )
        experiment = row.scalar_one_or_none()
        if experiment is None:
            return

        if is_candidate:
            results = list(experiment.candidate_results or [])
            results.append(score)
            await self.session.execute(
                update(EvolutionExperiment)
                .where(EvolutionExperiment.experiment_id == experiment_id)
                .values(candidate_results=results)
            )
        else:
            results = list(experiment.control_results or [])
            results.append(score)
            await self.session.execute(
                update(EvolutionExperiment)
                .where(EvolutionExperiment.experiment_id == experiment_id)
                .values(control_results=results)
            )
        await self.session.flush()

    # ── Memory ─────────────────────────────────────────────────────────────

    async def save_memory(
        self,
        agent_id: str,
        memory_type: str,
        key: str,
        value: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> EvolutionMemory:
        """Upsert a memory entry on (agent_id, key)."""
        result = await self.session.execute(
            select(EvolutionMemory)
            .where(EvolutionMemory.agent_id == agent_id)
            .where(EvolutionMemory.key == key)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            await self.session.execute(
                update(EvolutionMemory)
                .where(EvolutionMemory.id == existing.id)
                .values(
                    memory_type=memory_type,
                    value=value,
                    ttl_seconds=ttl_seconds,
                    updated_at=datetime.now(UTC),
                )
            )
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        row = EvolutionMemory(
            agent_id=agent_id,
            memory_type=memory_type,
            key=key,
            value=value,
            ttl_seconds=ttl_seconds,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_memory(
        self, agent_id: str, key: str
    ) -> Optional[EvolutionMemory]:
        """Return a single memory entry or None."""
        result = await self.session.execute(
            select(EvolutionMemory)
            .where(EvolutionMemory.agent_id == agent_id)
            .where(EvolutionMemory.key == key)
        )
        return result.scalar_one_or_none()

    async def get_agent_memories(
        self, agent_id: str, memory_type: Optional[str] = None
    ) -> list[EvolutionMemory]:
        """Return all memory entries for an agent, optionally filtered by type."""
        query = select(EvolutionMemory).where(
            EvolutionMemory.agent_id == agent_id
        )
        if memory_type is not None:
            query = query.where(EvolutionMemory.memory_type == memory_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_memory(self, agent_id: str, key: str) -> None:
        """Delete a memory entry by agent_id and key."""
        await self.session.execute(
            delete(EvolutionMemory)
            .where(EvolutionMemory.agent_id == agent_id)
            .where(EvolutionMemory.key == key)
        )
        await self.session.flush()
