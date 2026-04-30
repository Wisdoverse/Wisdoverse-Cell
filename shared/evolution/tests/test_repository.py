"""
Tests for EvolutionRepository — TDD: written before implementation.

Uses SQLite in-memory via conftest.py fixtures.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.evolution.db.repository import EvolutionRepository

# ── Skill Config Tests ─────────────────────────────────────────────────────


class TestSkillConfig:
    """Save and retrieve skill configurations."""

    @pytest.mark.asyncio
    async def test_save_and_get_active_skill(self, db_session: AsyncSession):
        """Save a skill config as active and retrieve it."""
        repo = EvolutionRepository(db_session)

        row = await repo.save_skill_config(
            skill_id="decompose-task",
            version="1",
            status="active",
            system_prompt="You are a task decomposition expert.",
            parameters={"temperature": 0.3},
            few_shot_examples=[{"input": "big task", "output": "subtasks"}],
            output_format="json",
            target_model="claude-sonnet-4-20250514",
        )
        assert row.id is not None
        assert row.skill_id == "decompose-task"
        assert row.version == "1"
        assert row.status == "active"

        active = await repo.get_active_skill("decompose-task")
        assert active is not None
        assert active.skill_id == "decompose-task"
        assert active.system_prompt == "You are a task decomposition expert."
        assert active.parameters == {"temperature": 0.3}
        assert active.few_shot_examples == [{"input": "big task", "output": "subtasks"}]
        assert active.output_format == "json"
        assert active.target_model == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_get_active_returns_none_for_missing(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)
        active = await repo.get_active_skill("nonexistent-skill")
        assert active is None

    @pytest.mark.asyncio
    async def test_get_skill_by_version(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)
        await repo.save_skill_config(
            skill_id="risk-analysis",
            version="2",
            status="candidate",
            system_prompt="Analyze risks.",
        )
        row = await repo.get_skill_by_version("risk-analysis", "2")
        assert row is not None
        assert row.version == "2"
        assert row.status == "candidate"

    @pytest.mark.asyncio
    async def test_promote_skill_retires_previous_active(self, db_session: AsyncSession):
        """Promoting a candidate retires the current active version."""
        repo = EvolutionRepository(db_session)

        # Create v1 as active
        await repo.save_skill_config(
            skill_id="decompose-task",
            version="1",
            status="active",
            system_prompt="V1 prompt.",
        )
        # Create v2 as candidate
        await repo.save_skill_config(
            skill_id="decompose-task",
            version="2",
            status="candidate",
            system_prompt="V2 prompt.",
        )

        # Promote v2
        await repo.promote_skill("decompose-task", "2")

        # v2 is now active
        active = await repo.get_active_skill("decompose-task")
        assert active is not None
        assert active.version == "2"
        assert active.status == "active"
        assert active.promoted_at is not None

        # v1 is now retired
        v1 = await repo.get_skill_by_version("decompose-task", "1")
        assert v1 is not None
        assert v1.status == "retired"

    @pytest.mark.asyncio
    async def test_get_previous_active(self, db_session: AsyncSession):
        """get_previous_active returns the most recently retired config."""
        repo = EvolutionRepository(db_session)

        await repo.save_skill_config(
            skill_id="decompose-task",
            version="1",
            status="active",
            system_prompt="V1.",
        )
        await repo.save_skill_config(
            skill_id="decompose-task",
            version="2",
            status="candidate",
            system_prompt="V2.",
        )
        await repo.promote_skill("decompose-task", "2")

        prev = await repo.get_previous_active("decompose-task")
        assert prev is not None
        assert prev.version == "1"
        assert prev.status == "retired"

    @pytest.mark.asyncio
    async def test_defaults(self, db_session: AsyncSession):
        """Skill configs have correct defaults."""
        repo = EvolutionRepository(db_session)
        row = await repo.save_skill_config(
            skill_id="test-skill",
            version="1",
            system_prompt="Test.",
        )
        assert row.status == "candidate"
        assert row.total_executions == 0
        assert row.success_rate == 0.0
        assert row.avg_human_rating == 0.0
        assert row.output_format == ""
        assert row.target_model == ""
        assert row.promoted_at is None
        assert row.created_at is not None


# ── Trace Tests ────────────────────────────────────────────────────────────


class TestTraces:
    """Save and query execution traces."""

    @pytest.mark.asyncio
    async def test_save_and_query_traces_by_agent(self, db_session: AsyncSession):
        """Save traces and retrieve them by agent_id."""
        repo = EvolutionRepository(db_session)
        now = datetime.now(UTC)

        await repo.save_trace(
            trace_id="t1",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            started_at=now,
            completed_at=now + timedelta(seconds=1),
            success=True,
            skill_used="decompose-task",
        )
        await repo.save_trace(
            trace_id="t2",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            started_at=now,
            completed_at=now + timedelta(seconds=2),
            success=False,
            error="LLM timeout",
            skill_used="decompose-task",
        )
        await repo.save_trace(
            trace_id="t3",
            agent_id="chat-agent",
            event_type="chat.query",
            started_at=now,
            success=True,
        )

        pm_traces = await repo.get_recent_traces("pjm-agent")
        assert len(pm_traces) == 2
        assert all(t.agent_id == "pjm-agent" for t in pm_traces)

        chat_traces = await repo.get_recent_traces("chat-agent")
        assert len(chat_traces) == 1

    @pytest.mark.asyncio
    async def test_query_traces_filtered_by_skill(self, db_session: AsyncSession):
        """get_recent_traces can filter by skill_id."""
        repo = EvolutionRepository(db_session)
        now = datetime.now(UTC)

        await repo.save_trace(
            trace_id="t1",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            started_at=now,
            success=True,
            skill_used="decompose-task",
        )
        await repo.save_trace(
            trace_id="t2",
            agent_id="pjm-agent",
            event_type="pm.report",
            started_at=now,
            success=True,
            skill_used="generate-report",
        )

        decompose_traces = await repo.get_recent_traces(
            "pjm-agent", skill_id="decompose-task"
        )
        assert len(decompose_traces) == 1
        assert decompose_traces[0].skill_used == "decompose-task"

    @pytest.mark.asyncio
    async def test_calc_success_rate(self, db_session: AsyncSession):
        """Calculate success rate from recent traces."""
        repo = EvolutionRepository(db_session)
        now = datetime.now(UTC)

        # 3 successes, 1 failure = 75% success
        for i, success in enumerate([True, True, True, False]):
            await repo.save_trace(
                trace_id=f"t{i}",
                agent_id="pjm-agent",
                event_type="pm.decompose",
                started_at=now,
                success=success,
                skill_used="decompose-task",
            )

        rate = await repo.calc_success_rate("pjm-agent", skill_id="decompose-task")
        assert rate == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_calc_success_rate_no_traces(self, db_session: AsyncSession):
        """Success rate is 0.0 when no traces exist."""
        repo = EvolutionRepository(db_session)
        rate = await repo.calc_success_rate("nonexistent-agent")
        assert rate == 0.0

    @pytest.mark.asyncio
    async def test_trace_with_json_fields(self, db_session: AsyncSession):
        """JSON fields (input_event, output_events, llm_calls) round-trip correctly."""
        repo = EvolutionRepository(db_session)
        now = datetime.now(UTC)

        input_evt = {"type": "pm.decompose", "payload": {"task": "build feature"}}
        output_evts = [{"type": "pm.subtask", "payload": {"id": 1}}]
        llm_data = [{"model": "claude-sonnet-4-20250514", "tokens": 500}]

        row = await repo.save_trace(
            trace_id="t_json",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            input_event=input_evt,
            output_events=output_evts,
            llm_calls=llm_data,
            started_at=now,
            success=True,
        )
        assert row.input_event == input_evt
        assert row.output_events == output_evts
        assert row.llm_calls == llm_data

    @pytest.mark.asyncio
    async def test_trace_limit(self, db_session: AsyncSession):
        """get_recent_traces respects the limit parameter."""
        repo = EvolutionRepository(db_session)
        now = datetime.now(UTC)

        for i in range(10):
            await repo.save_trace(
                trace_id=f"t{i}",
                agent_id="pjm-agent",
                event_type="pm.decompose",
                started_at=now,
                success=True,
            )

        traces = await repo.get_recent_traces("pjm-agent", limit=3)
        assert len(traces) == 3


# ── Reflection Tests ───────────────────────────────────────────────────────


class TestReflections:
    """Save and retrieve reflection records."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_reflection(self, db_session: AsyncSession):
        """Save a reflection and verify its fields."""
        repo = EvolutionRepository(db_session)

        row = await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            success_patterns=["Fast on simple tasks"],
            failure_patterns=["Slow on complex tasks"],
            optimization_suggestions=["Add caching layer"],
            human_corrections_summary="Users want shorter output.",
        )
        assert row.id is not None
        assert row.agent_id == "pjm-agent"
        assert row.skill_id == "decompose-task"
        assert row.success_patterns == ["Fast on simple tasks"]
        assert row.failure_patterns == ["Slow on complex tasks"]
        assert row.optimization_suggestions == ["Add caching layer"]
        assert row.human_corrections_summary == "Users want shorter output."
        assert row.created_at is not None

    @pytest.mark.asyncio
    async def test_reflection_defaults(self, db_session: AsyncSession):
        """Reflection defaults are applied correctly."""
        repo = EvolutionRepository(db_session)
        row = await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
        )
        assert row.success_patterns == []
        assert row.failure_patterns == []
        assert row.optimization_suggestions == []
        assert row.human_corrections_summary == ""

    @pytest.mark.asyncio
    async def test_get_recent_reflections(self, db_session: AsyncSession):
        """get_recent_reflections saves 3 reflections and retrieves latest 2."""
        repo = EvolutionRepository(db_session)

        # Save 3 reflections in order
        r1 = await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            success_patterns=["Pattern A"],
            optimization_suggestions=["Suggestion A"],
        )
        r2 = await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            success_patterns=["Pattern B"],
            optimization_suggestions=["Suggestion B"],
        )
        r3 = await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            success_patterns=["Pattern C"],
            optimization_suggestions=["Suggestion C"],
        )

        # Retrieve latest 2 (most recent first)
        recent = await repo.get_recent_reflections(
            agent_id="pjm-agent", skill_id="decompose-task", limit=2
        )

        assert len(recent) == 2
        # Most recent (r3) should come first (ordered by created_at desc)
        ids = [r.id for r in recent]
        assert r3.id in ids
        assert r2.id in ids
        assert r1.id not in ids

    @pytest.mark.asyncio
    async def test_get_recent_reflections_filters_by_agent_and_skill(
        self, db_session: AsyncSession
    ):
        """get_recent_reflections returns only rows matching agent_id + skill_id."""
        repo = EvolutionRepository(db_session)

        # Save for pjm-agent / decompose-task
        await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            success_patterns=["PM pattern"],
        )
        # Save for a different agent
        await repo.save_reflection(
            agent_id="chat-agent",
            skill_id="decompose-task",
            success_patterns=["Chat pattern"],
        )
        # Save for a different skill
        await repo.save_reflection(
            agent_id="pjm-agent",
            skill_id="generate-report",
            success_patterns=["Report pattern"],
        )

        results = await repo.get_recent_reflections(
            agent_id="pjm-agent", skill_id="decompose-task", limit=10
        )

        assert len(results) == 1
        assert results[0].agent_id == "pjm-agent"
        assert results[0].skill_id == "decompose-task"
        assert results[0].success_patterns == ["PM pattern"]

    @pytest.mark.asyncio
    async def test_get_recent_reflections_returns_empty_when_none(
        self, db_session: AsyncSession
    ):
        """get_recent_reflections returns empty list when no records exist."""
        repo = EvolutionRepository(db_session)
        results = await repo.get_recent_reflections(
            agent_id="nonexistent-agent", skill_id="nonexistent-skill"
        )
        assert results == []


# ── Experiment Tests ──────────────────────────────────────────────────────


class TestExperimentRepo:
    """Save, query, and manage experiments."""

    @pytest.mark.asyncio
    async def test_save_and_get_active_experiment(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        row = await repo.save_experiment(
            experiment_id="exp_001",
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
            traffic_pct=15,
        )
        assert row.id is not None
        assert row.experiment_id == "exp_001"
        assert row.status == "running"
        assert row.control_results == []
        assert row.candidate_results == []

        active = await repo.get_active_experiment("pjm-agent", "decompose-task")
        assert active is not None
        assert active.experiment_id == "exp_001"
        assert active.traffic_pct == 15

    @pytest.mark.asyncio
    async def test_get_active_experiment_returns_none(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)
        active = await repo.get_active_experiment("nonexistent", "nonexistent")
        assert active is None

    @pytest.mark.asyncio
    async def test_conclude_experiment(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        await repo.save_experiment(
            experiment_id="exp_002",
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
        )

        now = datetime.now(UTC)
        await repo.conclude_experiment("exp_002", "concluded", concluded_at=now)

        # No longer active
        active = await repo.get_active_experiment("pjm-agent", "decompose-task")
        assert active is None

    @pytest.mark.asyncio
    async def test_add_experiment_results(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        await repo.save_experiment(
            experiment_id="exp_003",
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
        )

        await repo.add_experiment_result("exp_003", is_candidate=False, score=0.8)
        await repo.add_experiment_result("exp_003", is_candidate=False, score=0.9)
        await repo.add_experiment_result("exp_003", is_candidate=True, score=0.85)

        active = await repo.get_active_experiment("pjm-agent", "decompose-task")
        assert active is not None
        assert active.control_results == [0.8, 0.9]
        assert active.candidate_results == [0.85]

    @pytest.mark.asyncio
    async def test_experiment_defaults(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        row = await repo.save_experiment(
            experiment_id="exp_004",
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
        )
        assert row.traffic_pct == 10
        assert row.min_samples == 50
        assert row.max_duration_hours == 72
        assert row.success_metric == "success_rate"
        assert row.min_improvement == 0.05
        assert row.concluded_at is None
        assert row.created_at is not None


# ── Memory Tests ──────────────────────────────────────────────────────────


class TestMemoryRepo:
    """Save, query, upsert, and delete memory entries."""

    @pytest.mark.asyncio
    async def test_save_and_get_memory(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        row = await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="short_term",
            key="last_task",
            value={"task_id": "t1"},
            ttl_seconds=3600,
        )
        assert row.id is not None
        assert row.agent_id == "pjm-agent"
        assert row.key == "last_task"
        assert row.value == {"task_id": "t1"}
        assert row.ttl_seconds == 3600

        fetched = await repo.get_memory("pjm-agent", "last_task")
        assert fetched is not None
        assert fetched.value == {"task_id": "t1"}

    @pytest.mark.asyncio
    async def test_get_memory_returns_none(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)
        fetched = await repo.get_memory("nonexistent", "nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_upsert_on_conflict(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="short_term",
            key="counter",
            value={"count": 1},
        )

        # Upsert with new value
        await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="long_term",
            key="counter",
            value={"count": 2},
        )

        fetched = await repo.get_memory("pjm-agent", "counter")
        assert fetched is not None
        assert fetched.value == {"count": 2}
        assert fetched.memory_type == "long_term"

    @pytest.mark.asyncio
    async def test_get_agent_memories_by_type(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="short_term",
            key="key1",
            value={"data": "a"},
        )
        await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="long_term",
            key="key2",
            value={"data": "b"},
        )
        await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="short_term",
            key="key3",
            value={"data": "c"},
        )

        all_memories = await repo.get_agent_memories("pjm-agent")
        assert len(all_memories) == 3

        short_term = await repo.get_agent_memories("pjm-agent", memory_type="short_term")
        assert len(short_term) == 2

        long_term = await repo.get_agent_memories("pjm-agent", memory_type="long_term")
        assert len(long_term) == 1

    @pytest.mark.asyncio
    async def test_delete_memory(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)

        await repo.save_memory(
            agent_id="pjm-agent",
            memory_type="short_term",
            key="to_delete",
            value={"tmp": True},
        )

        fetched = await repo.get_memory("pjm-agent", "to_delete")
        assert fetched is not None

        await repo.delete_memory("pjm-agent", "to_delete")

        fetched = await repo.get_memory("pjm-agent", "to_delete")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_memory_no_error(self, db_session: AsyncSession):
        repo = EvolutionRepository(db_session)
        # Should not raise
        await repo.delete_memory("pjm-agent", "nonexistent")
