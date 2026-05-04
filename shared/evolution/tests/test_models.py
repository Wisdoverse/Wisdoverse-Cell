"""Tests for evolution data models — TDD: written before implementation."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from shared.evolution.models import (
    ExecutionTrace,
    Experiment,
    ExperimentStatus,
    LLMCallRecord,
    MemoryEntry,
    MemoryType,
    Reflection,
    SkillConfig,
    SkillStatus,
)

# ── LLMCallRecord ──────────────────────────────────────────────────────────


class TestLLMCallRecord:
    """LLMCallRecord tracks a single LLM API call."""

    def test_create_minimal(self):
        record = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=320.5,
            success=True,
        )
        assert record.model_id == "claude-sonnet-4-20250514"
        assert record.prompt_tokens == 100
        assert record.completion_tokens == 50
        assert record.latency_ms == 320.5
        assert record.success is True
        assert record.call_id.startswith("llm_")

    def test_cost_claude_opus(self):
        """claude-opus-4-6: $15/M input + $75/M output."""
        record = LLMCallRecord(
            model_id="claude-opus-4-6",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            latency_ms=5000.0,
            success=True,
        )
        assert record.cost_usd == pytest.approx(15.0 + 75.0)

    def test_cost_claude_sonnet(self):
        """claude-sonnet-4-20250514: $3/M input + $15/M output."""
        record = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            latency_ms=3000.0,
            success=True,
        )
        assert record.cost_usd == pytest.approx(3.0 + 15.0)

    def test_cost_claude_haiku(self):
        """claude-haiku-4-5-20251001: $0.80/M input + $4/M output."""
        record = LLMCallRecord(
            model_id="claude-haiku-4-5-20251001",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            latency_ms=1000.0,
            success=True,
        )
        assert record.cost_usd == pytest.approx(0.80 + 4.0)

    def test_cost_unknown_model_zero(self):
        """Unknown models should return 0.0 cost."""
        record = LLMCallRecord(
            model_id="unknown-model",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=200.0,
            success=True,
        )
        assert record.cost_usd == 0.0

    def test_cost_small_tokens(self):
        """Cost calculation with small token counts."""
        record = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=250.0,
            success=True,
        )
        expected = (500 * 3.0 / 1_000_000) + (200 * 15.0 / 1_000_000)
        assert record.cost_usd == pytest.approx(expected)

    def test_serialization_roundtrip(self):
        record = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=320.5,
            success=True,
        )
        json_str = record.model_dump_json()
        restored = LLMCallRecord.model_validate_json(json_str)
        assert restored.model_id == record.model_id
        assert restored.cost_usd == record.cost_usd

    def test_failed_call(self):
        record = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=100,
            completion_tokens=0,
            latency_ms=50.0,
            success=False,
            error="Rate limit exceeded",
        )
        assert record.success is False
        assert record.error == "Rate limit exceeded"

    def test_called_at_field(self):
        record = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=320.5,
            success=True,
        )
        assert record.called_at is not None
        assert record.called_at <= datetime.now(UTC)


# ── SkillConfig ─────────────────────────────────────────────────────────────


class TestSkillConfig:
    """SkillConfig is a versioned skill configuration."""

    def test_create_minimal(self):
        skill = SkillConfig(
            skill_id="decompose-task",
            version=1,
            system_prompt="You are a task decomposition expert.",
        )
        assert skill.skill_id == "decompose-task"
        assert skill.version == 1
        assert skill.status == SkillStatus.ACTIVE
        assert skill.system_prompt == "You are a task decomposition expert."
        assert skill.parameters == {}
        assert skill.few_shot_examples == []
        assert skill.output_format is None
        assert skill.target_model is None
        assert skill.total_executions == 0
        assert skill.success_rate == 0.0
        assert skill.avg_human_rating == 0.0
        assert skill.promoted_at is None

    def test_status_enum_values(self):
        assert SkillStatus.ACTIVE == "active"
        assert SkillStatus.CANDIDATE == "candidate"
        assert SkillStatus.RETIRED == "retired"

    def test_full_config(self):
        now = datetime.now(UTC)
        skill = SkillConfig(
            skill_id="risk-analysis",
            version=3,
            status=SkillStatus.CANDIDATE,
            system_prompt="Analyze project risks.",
            parameters={"temperature": 0.3, "max_tokens": 2000},
            few_shot_examples=[
                {"input": "project delay", "output": "HIGH risk"},
            ],
            output_format="json",
            target_model="claude-sonnet-4-20250514",
            total_executions=50,
            success_rate=0.92,
            avg_human_rating=4.2,
            promoted_at=now,
            created_at=now,
        )
        assert skill.status == SkillStatus.CANDIDATE
        assert skill.parameters["temperature"] == 0.3
        assert len(skill.few_shot_examples) == 1
        assert skill.output_format == "json"
        assert skill.target_model == "claude-sonnet-4-20250514"
        assert skill.total_executions == 50
        assert skill.success_rate == 0.92
        assert skill.avg_human_rating == 4.2
        assert skill.promoted_at == now

    def test_timestamps_auto_set(self):
        skill = SkillConfig(
            skill_id="test-skill",
            version=1,
            system_prompt="test",
        )
        assert skill.created_at is not None
        assert skill.created_at <= datetime.now(UTC)

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            SkillConfig(
                skill_id="test",
                version=1,
                system_prompt="test",
                status="invalid_status",
            )

    def test_serialization_roundtrip(self):
        skill = SkillConfig(
            skill_id="decompose-task",
            version=2,
            status=SkillStatus.ACTIVE,
            system_prompt="Decompose tasks.",
            parameters={"temperature": 0.5},
            few_shot_examples=[{"in": "a", "out": "b"}],
        )
        json_str = skill.model_dump_json()
        restored = SkillConfig.model_validate_json(json_str)
        assert restored.skill_id == skill.skill_id
        assert restored.version == skill.version
        assert restored.parameters == skill.parameters


# ── ExecutionTrace ──────────────────────────────────────────────────────────


class TestExecutionTrace:
    """ExecutionTrace records one full handle_event execution."""

    def test_create_minimal(self):
        trace = ExecutionTrace(
            trace_id="trace_abc123",
            agent_id="pjm-agent",
            event_type="pm.decompose",
        )
        assert trace.trace_id == "trace_abc123"
        assert trace.agent_id == "pjm-agent"
        assert trace.event_type == "pm.decompose"
        assert trace.llm_calls == []
        assert trace.success is True
        assert trace.error is None
        assert trace.output_events == []
        assert trace.human_rating is None
        assert trace.human_correction is None
        assert trace.auto_score is None

    def test_duration_ms_computed(self):
        start = datetime(2026, 3, 18, 10, 0, 0, tzinfo=UTC)
        end = start + timedelta(milliseconds=1500)
        trace = ExecutionTrace(
            trace_id="trace_dur",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            started_at=start,
            completed_at=end,
        )
        assert trace.duration_ms == pytest.approx(1500.0)

    def test_duration_ms_none_when_incomplete(self):
        trace = ExecutionTrace(
            trace_id="trace_inc",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            completed_at=None,
        )
        assert trace.duration_ms is None

    def test_full_trace(self):
        llm_call = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=800.0,
            success=True,
        )
        start = datetime.now(UTC)
        trace = ExecutionTrace(
            trace_id="trace_full",
            agent_id="chat-agent",
            event_type="chat.pm-query",
            input_event={"type": "chat.pm-query", "payload": {"q": "status?"}},
            output_events=[{"type": "chat.pm-response", "payload": {"a": "ok"}}],
            llm_calls=[llm_call],
            skill_used="answer-query",
            skill_version=2,
            started_at=start,
            completed_at=start + timedelta(seconds=1),
            success=True,
            human_rating=None,
            human_correction=None,
        )
        assert len(trace.llm_calls) == 1
        assert trace.skill_used == "answer-query"
        assert trace.skill_version == 2
        assert trace.duration_ms == pytest.approx(1000.0)

    def test_failed_trace(self):
        trace = ExecutionTrace(
            trace_id="trace_fail",
            agent_id="sync-agent",
            event_type="sync.trigger",
            success=False,
            error="Connection timeout to Feishu API",
        )
        assert trace.success is False
        assert trace.error == "Connection timeout to Feishu API"

    def test_human_feedback(self):
        trace = ExecutionTrace(
            trace_id="trace_fb",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            human_rating=4,
            human_correction="Good decomposition, minor overlap.",
            auto_score=0.85,
        )
        assert trace.human_rating == 4
        assert trace.human_correction == "Good decomposition, minor overlap."
        assert trace.auto_score == 0.85

    def test_serialization_roundtrip(self):
        llm_call = LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=300.0,
            success=True,
        )
        start = datetime.now(UTC)
        trace = ExecutionTrace(
            trace_id="trace_ser",
            agent_id="pjm-agent",
            event_type="pm.decompose",
            llm_calls=[llm_call],
            started_at=start,
            completed_at=start + timedelta(milliseconds=750),
        )
        json_str = trace.model_dump_json()
        restored = ExecutionTrace.model_validate_json(json_str)
        assert restored.trace_id == trace.trace_id
        assert restored.duration_ms == pytest.approx(750.0)
        assert len(restored.llm_calls) == 1


# ── Reflection ──────────────────────────────────────────────────────────────


class TestReflection:
    """Reflection is the output of self-reflector analysis."""

    def test_create_minimal(self):
        reflection = Reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
        )
        assert reflection.agent_id == "pjm-agent"
        assert reflection.skill_id == "decompose-task"
        assert reflection.success_patterns == []
        assert reflection.failure_patterns == []
        assert reflection.optimization_suggestions == []
        assert reflection.human_corrections_summary == ""
        assert reflection.reflection_id.startswith("ref_")

    def test_with_patterns_and_suggestions(self):
        reflection = Reflection(
            agent_id="chat-agent",
            skill_id="answer-query",
            success_patterns=[
                "Fast response on simple queries (<500ms avg)",
            ],
            failure_patterns=[
                "High latency on complex queries (>2s avg)",
                "Token usage spikes on multi-turn conversations",
            ],
            optimization_suggestions=[
                "Add query classification step to route simple vs complex",
                "Implement conversation summarization for long threads",
            ],
            human_corrections_summary="Users prefer shorter responses for status queries.",
        )
        assert len(reflection.success_patterns) == 1
        assert len(reflection.failure_patterns) == 2
        assert len(reflection.optimization_suggestions) == 2
        assert "latency" in reflection.failure_patterns[0].lower()
        assert reflection.human_corrections_summary != ""

    def test_timestamps(self):
        reflection = Reflection(
            agent_id="pjm-agent",
            skill_id="decompose-task",
        )
        assert reflection.created_at is not None
        assert reflection.created_at <= datetime.now(UTC)

    def test_serialization_roundtrip(self):
        reflection = Reflection(
            agent_id="analysis-agent",
            skill_id="risk-detection",
            success_patterns=["Caught 7 out of 10 risks correctly"],
            failure_patterns=["Missed 3 out of 10 risks in test set"],
            optimization_suggestions=["Fine-tune risk keywords", "Add industry-specific examples"],
        )
        json_str = reflection.model_dump_json()
        restored = Reflection.model_validate_json(json_str)
        assert restored.agent_id == reflection.agent_id
        assert restored.success_patterns == reflection.success_patterns
        assert restored.failure_patterns == reflection.failure_patterns
        assert restored.optimization_suggestions == reflection.optimization_suggestions


# ── Experiment ─────────────────────────────────────────────────────────────


class TestExperiment:
    """Experiment tracks an A/B test between two skill versions."""

    def test_create_minimal(self):
        exp = Experiment(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
        )
        assert exp.experiment_id.startswith("exp_")
        assert exp.agent_id == "pjm-agent"
        assert exp.skill_id == "decompose-task"
        assert exp.control_version == 1
        assert exp.candidate_version == 2
        assert exp.traffic_pct == 10
        assert exp.min_samples == 50
        assert exp.max_duration_hours == 72
        assert exp.success_metric == "success_rate"
        assert exp.min_improvement == 0.05
        assert exp.status == ExperimentStatus.RUNNING
        assert exp.concluded_at is None

    def test_traffic_pct_at_30_allowed(self):
        exp = Experiment(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
            traffic_pct=30,
        )
        assert exp.traffic_pct == 30

    def test_traffic_pct_over_30_rejected(self):
        with pytest.raises(ValidationError):
            Experiment(
                agent_id="pjm-agent",
                skill_id="decompose-task",
                control_version=1,
                candidate_version=2,
                traffic_pct=31,
            )

    def test_status_transitions(self):
        exp = Experiment(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
        )
        assert exp.status == ExperimentStatus.RUNNING

        concluded = exp.model_copy(
            update={
                "status": ExperimentStatus.CONCLUDED,
                "concluded_at": datetime.now(UTC),
            }
        )
        assert concluded.status == ExperimentStatus.CONCLUDED
        assert concluded.concluded_at is not None

        promoted = exp.model_copy(update={"status": ExperimentStatus.PROMOTED})
        assert promoted.status == ExperimentStatus.PROMOTED

        rolled_back = exp.model_copy(
            update={"status": ExperimentStatus.ROLLED_BACK}
        )
        assert rolled_back.status == ExperimentStatus.ROLLED_BACK

    def test_status_enum_values(self):
        assert ExperimentStatus.RUNNING == "running"
        assert ExperimentStatus.PROMOTED == "promoted"
        assert ExperimentStatus.CONCLUDED == "concluded"
        assert ExperimentStatus.ROLLED_BACK == "rolled_back"

    def test_timestamps_auto_set(self):
        exp = Experiment(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
        )
        assert exp.created_at is not None
        assert exp.created_at <= datetime.now(UTC)

    def test_serialization_roundtrip(self):
        exp = Experiment(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            control_version=1,
            candidate_version=2,
            traffic_pct=20,
        )
        json_str = exp.model_dump_json()
        restored = Experiment.model_validate_json(json_str)
        assert restored.experiment_id == exp.experiment_id
        assert restored.traffic_pct == 20
        assert restored.status == ExperimentStatus.RUNNING


# ── MemoryEntry ────────────────────────────────────────────────────────────


class TestMemoryEntry:
    """MemoryEntry is a key-value memory store for agents."""

    def test_create_minimal(self):
        entry = MemoryEntry(
            agent_id="pjm-agent",
            memory_type=MemoryType.SHORT_TERM,
            key="last_task",
            value={"task_id": "t1"},
        )
        assert entry.agent_id == "pjm-agent"
        assert entry.memory_type == MemoryType.SHORT_TERM
        assert entry.key == "last_task"
        assert entry.value == {"task_id": "t1"}
        assert entry.ttl_seconds is None

    def test_with_ttl(self):
        entry = MemoryEntry(
            agent_id="pjm-agent",
            memory_type=MemoryType.SHORT_TERM,
            key="cache_key",
            value={"data": "cached"},
            ttl_seconds=3600,
        )
        assert entry.ttl_seconds == 3600

    def test_long_term_memory(self):
        entry = MemoryEntry(
            agent_id="chat-agent",
            memory_type=MemoryType.LONG_TERM,
            key="user_prefs",
            value={"language": "en", "tone": "formal"},
        )
        assert entry.memory_type == MemoryType.LONG_TERM

    def test_memory_type_enum_values(self):
        assert MemoryType.SHORT_TERM == "short_term"
        assert MemoryType.LONG_TERM == "long_term"

    def test_timestamps_auto_set(self):
        entry = MemoryEntry(
            agent_id="pjm-agent",
            memory_type=MemoryType.SHORT_TERM,
            key="test",
            value={},
        )
        assert entry.created_at is not None
        assert entry.created_at <= datetime.now(UTC)

    def test_serialization_roundtrip(self):
        entry = MemoryEntry(
            agent_id="pjm-agent",
            memory_type=MemoryType.LONG_TERM,
            key="skill_stats",
            value={"success_count": 42, "fail_count": 3},
            ttl_seconds=86400,
        )
        json_str = entry.model_dump_json()
        restored = MemoryEntry.model_validate_json(json_str)
        assert restored.agent_id == entry.agent_id
        assert restored.key == entry.key
        assert restored.value == entry.value
        assert restored.ttl_seconds == 86400
