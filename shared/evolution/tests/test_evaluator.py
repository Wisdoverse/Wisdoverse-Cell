"""
Tests for Evaluator — TDD: written before implementation.

Tests cover:
1. Structural: success with outputs → 1.0
2. Structural: success without outputs → 0.5
3. Structural: failure → 0.0
4. Human: rating 5 → 1.0, rating 1 → 0.0, rating 3 → 0.5
5. Human: None → uses structural+semantic average
6. Semantic: LLM returns "0.8" → 0.8
7. Semantic: LLM error → falls back to structural score
8. Aggregate: average of multiple traces
9. Aggregate: empty list → 0.0
10. Compliance: no format defined → 1.0
11. Compliance: no output events → 0.0
12. Compliance: no LLM → 1.0 (fail-open)
13. Compliance: LLM returns "0.8" → 0.8
14. Compliance: LLM error → 1.0 (fail-open)
15. score_trace with skill_config: all 4 signals combined
16. score_trace backwards compatible: no skill_config works same as before
17. Default weights include compliance and sum to 1.0
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.evolution.evaluator import Evaluator


def make_skill_config(output_format: str | None = "JSON") -> MagicMock:
    """Return a MagicMock SkillConfig with the given output_format."""
    skill_config = MagicMock()
    skill_config.output_format = output_format
    return skill_config

# ── Helpers ────────────────────────────────────────────────────────────────


def make_trace(
    *,
    success: bool = True,
    output_events: list | None = None,
    error: str | None = None,
    human_rating: int | None = None,
    input_event: dict | None = None,
) -> MagicMock:
    """Return a MagicMock trace with the given attributes."""
    trace = MagicMock()
    trace.success = success
    trace.output_events = output_events if output_events is not None else []
    trace.error = error
    trace.human_rating = human_rating
    trace.input_event = input_event or {"event_type": "test.event"}
    return trace


def make_llm_gateway(response: str = "0.8") -> AsyncMock:
    """Return a mock LLM gateway whose complete() returns a score string."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


# ── Test: _score_structural ─────────────────────────────────────────────────


class TestScoreStructural:
    """_score_structural returns 1.0/0.5/0.0 based on success + output_events."""

    def test_success_with_output_events_returns_1(self):
        """success=True and output_events non-empty → 1.0."""
        evaluator = Evaluator()
        trace = make_trace(success=True, output_events=[{"event_type": "task.done"}])

        score = evaluator._score_structural(trace)

        assert score == 1.0

    def test_success_without_output_events_returns_half(self):
        """success=True but output_events empty → 0.5."""
        evaluator = Evaluator()
        trace = make_trace(success=True, output_events=[])

        score = evaluator._score_structural(trace)

        assert score == 0.5

    def test_failure_returns_zero(self):
        """success=False → 0.0 regardless of output_events."""
        evaluator = Evaluator()
        trace = make_trace(success=False, error="Something broke")

        score = evaluator._score_structural(trace)

        assert score == 0.0

    def test_failure_with_output_events_still_zero(self):
        """Even if there are output_events, failure means 0.0."""
        evaluator = Evaluator()
        trace = make_trace(
            success=False, output_events=[{"event_type": "task.done"}], error="error"
        )

        score = evaluator._score_structural(trace)

        assert score == 0.0


# ── Test: _score_human ──────────────────────────────────────────────────────


class TestScoreHuman:
    """_score_human normalizes 1-5 ratings to 0.0-1.0."""

    def test_rating_5_returns_1(self):
        """Rating 5 (max) → 1.0."""
        evaluator = Evaluator()
        trace = make_trace(human_rating=5)

        score = evaluator._score_human(trace)

        assert score == 1.0

    def test_rating_1_returns_0(self):
        """Rating 1 (min) → 0.0."""
        evaluator = Evaluator()
        trace = make_trace(human_rating=1)

        score = evaluator._score_human(trace)

        assert score == 0.0

    def test_rating_3_returns_half(self):
        """Rating 3 (middle) → 0.5."""
        evaluator = Evaluator()
        trace = make_trace(human_rating=3)

        score = evaluator._score_human(trace)

        assert score == 0.5

    def test_rating_none_returns_none(self):
        """No rating → None (not scored)."""
        evaluator = Evaluator()
        trace = make_trace(human_rating=None)

        score = evaluator._score_human(trace)

        assert score is None

    def test_rating_2_returns_quarter(self):
        """Rating 2 → 0.25."""
        evaluator = Evaluator()
        trace = make_trace(human_rating=2)

        score = evaluator._score_human(trace)

        assert score == 0.25

    def test_rating_4_returns_three_quarters(self):
        """Rating 4 → 0.75."""
        evaluator = Evaluator()
        trace = make_trace(human_rating=4)

        score = evaluator._score_human(trace)

        assert score == 0.75


# ── Test: _score_semantic ────────────────────────────────────────────────────


class TestScoreSemantic:
    """_score_semantic uses LLM to evaluate output quality."""

    @pytest.mark.asyncio
    async def test_llm_returns_float_string(self):
        """LLM response '0.8' → 0.8."""
        llm = make_llm_gateway("0.8")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "task.done"}],
            input_event={"event_type": "task.create"},
        )

        score = await evaluator._score_semantic(trace)

        assert score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_llm_returns_score_with_whitespace(self):
        """LLM response '  0.6  ' (with whitespace) → 0.6."""
        llm = make_llm_gateway("  0.6  ")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(success=True)

        score = await evaluator._score_semantic(trace)

        assert score == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_structural(self):
        """LLM raises exception → returns structural score as fallback."""
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(success=True, output_events=[{"event_type": "task.done"}])

        score = await evaluator._score_semantic(trace)

        # Fallback is structural score: success + outputs → 1.0
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_llm_returns_non_float_falls_back_to_structural(self):
        """LLM returns unparseable string → falls back to structural score."""
        llm = make_llm_gateway("not a number")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(success=True, output_events=[])

        score = await evaluator._score_semantic(trace)

        # Fallback is structural score: success + no outputs → 0.5
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(self):
        """_score_semantic calls LLM with temperature=0, max_tokens=10."""
        llm = make_llm_gateway("0.9")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(success=True)

        await evaluator._score_semantic(trace)

        llm.complete.assert_awaited_once()
        call_kwargs = llm.complete.call_args.kwargs
        assert call_kwargs.get("temperature") == 0
        assert call_kwargs.get("max_tokens") == 10


# ── Test: score_trace ────────────────────────────────────────────────────────


class TestScoreTrace:
    """score_trace combines structural, semantic, and human signals."""

    @pytest.mark.asyncio
    async def test_no_human_rating_uses_structural_semantic_average(self):
        """No human_rating → (structural + semantic) / 2."""
        # No LLM → semantic falls back to structural
        evaluator = Evaluator(llm_gateway=None)
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator.score_trace(trace)

        # structural=1.0, semantic=structural=1.0 → (1.0+1.0)/2 = 1.0
        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_human_rating_failure_trace(self):
        """Failure trace, no human rating, no skill_config.
        structural=0.0, semantic=0.0 (fallback), compliance=1.0 (no format) → 1/3.
        """
        evaluator = Evaluator(llm_gateway=None)
        trace = make_trace(success=False, error="broken")

        score = await evaluator.score_trace(trace)

        # structural=0.0, semantic=0.0, compliance=1.0 (no constraint) → 1/3
        assert score == pytest.approx(1 / 3)

    @pytest.mark.asyncio
    async def test_with_human_rating_uses_weighted_sum(self):
        """All three signals combined using default weights."""
        llm = make_llm_gateway("1.0")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "done"}],
            human_rating=5,
        )

        score = await evaluator.score_trace(trace)

        # structural=1.0, semantic=1.0, compliance=1.0 (no skill_config), human=1.0
        # 0.25*1.0 + 0.25*1.0 + 0.15*1.0 + 0.35*1.0 = 1.0
        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_with_human_rating_low(self):
        """Low human rating pulls down overall score."""
        llm = make_llm_gateway("1.0")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "done"}],
            human_rating=1,
        )

        score = await evaluator.score_trace(trace)

        # structural=1.0, semantic=1.0, compliance=1.0 (no skill_config), human=0.0
        # 0.25*1.0 + 0.25*1.0 + 0.15*1.0 + 0.35*0.0 = 0.65
        assert score == pytest.approx(0.65)

    @pytest.mark.asyncio
    async def test_custom_weights_respected(self):
        """Custom weights are applied when provided."""
        llm = make_llm_gateway("0.0")
        evaluator = Evaluator(
            llm_gateway=llm,
            weights={"structural": 0.5, "semantic": 0.5, "human": 0.0},
        )
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "done"}],
            human_rating=5,
        )

        score = await evaluator.score_trace(trace)

        # structural=1.0, semantic=0.0, human=1.0
        # 0.5*1.0 + 0.5*0.0 + 0.0*1.0 = 0.5
        assert score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_no_llm_gateway_no_human_uses_structural_average(self):
        """With no LLM, semantic=structural, so average = structural."""
        evaluator = Evaluator(llm_gateway=None)
        trace = make_trace(success=True, output_events=[])

        score = await evaluator.score_trace(trace)

        # structural=0.5, semantic=0.5 (fallback), compliance=1.0 (no skill_config)
        # no human → (0.5 + 0.5 + 1.0) / 3 = 0.667
        assert score == pytest.approx(2 / 3)


# ── Test: aggregate_scores ────────────────────────────────────────────────────


class TestAggregateScores:
    """aggregate_scores averages scores across multiple traces."""

    @pytest.mark.asyncio
    async def test_empty_traces_returns_zero(self):
        """Empty list → 0.0."""
        evaluator = Evaluator()

        score = await evaluator.aggregate_scores([])

        assert score == 0.0

    @pytest.mark.asyncio
    async def test_single_trace_returns_its_score(self):
        """Single trace → its score."""
        evaluator = Evaluator(llm_gateway=None)
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator.aggregate_scores([trace])

        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_multiple_traces_averages_scores(self):
        """Multiple traces → average of individual scores."""
        evaluator = Evaluator(llm_gateway=None)
        # No skill_config → compliance=1.0 for all; no human rating → avg of 3 auto signals
        # success+outputs  → (1.0+1.0+1.0)/3 = 1.0
        # success+no_outputs → (0.5+0.5+1.0)/3 = 2/3
        # failure          → (0.0+0.0+1.0)/3 = 1/3
        traces = [
            make_trace(success=True, output_events=[{"event_type": "done"}]),
            make_trace(success=True, output_events=[]),
            make_trace(success=False, error="error"),
        ]

        score = await evaluator.aggregate_scores(traces)

        # (1.0 + 2/3 + 1/3) / 3 = (6/3) / 3 = 2/3
        assert score == pytest.approx(2 / 3)

    @pytest.mark.asyncio
    async def test_all_perfect_traces_returns_one(self):
        """All success+output traces → 1.0."""
        evaluator = Evaluator(llm_gateway=None)
        traces = [
            make_trace(success=True, output_events=[{"event_type": "done"}])
            for _ in range(5)
        ]

        score = await evaluator.aggregate_scores(traces)

        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_all_failed_traces_returns_low_score(self):
        """All failure traces, no skill_config → compliance=1.0 (fail-open), score=1/3."""
        evaluator = Evaluator(llm_gateway=None)
        traces = [make_trace(success=False, error="error") for _ in range(5)]

        score = await evaluator.aggregate_scores(traces)

        # structural=0.0, semantic=0.0 (fallback), compliance=1.0 (no constraint)
        # → (0.0 + 0.0 + 1.0) / 3 = 1/3
        assert score == pytest.approx(1 / 3)


# ── Test: _score_compliance ───────────────────────────────────────────────────


class TestScoreCompliance:
    """_score_compliance checks output adherence to SkillConfig.output_format."""

    @pytest.mark.asyncio
    async def test_compliance_no_format_defined(self):
        """skill_config with output_format=None → 1.0 (no constraint)."""
        evaluator = Evaluator(llm_gateway=None)
        skill_config = make_skill_config(output_format=None)
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator._score_compliance(trace, skill_config)

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_compliance_no_skill_config(self):
        """skill_config=None → 1.0 (no constraint to check)."""
        evaluator = Evaluator(llm_gateway=None)
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator._score_compliance(trace, None)

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_compliance_no_output(self):
        """output_format defined but no output_events → 0.0."""
        evaluator = Evaluator(llm_gateway=None)
        skill_config = make_skill_config(output_format="JSON")
        trace = make_trace(success=True, output_events=[])

        score = await evaluator._score_compliance(trace, skill_config)

        assert score == 0.0

    @pytest.mark.asyncio
    async def test_compliance_no_llm(self):
        """output_format defined, has output but no LLM → 1.0 (fail-open)."""
        evaluator = Evaluator(llm_gateway=None)
        skill_config = make_skill_config(output_format="JSON")
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator._score_compliance(trace, skill_config)

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_compliance_llm_scores(self):
        """LLM returns '0.8' → compliance score is 0.8."""
        llm = make_llm_gateway("0.8")
        evaluator = Evaluator(llm_gateway=llm)
        skill_config = make_skill_config(output_format="JSON with 'result' key")
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator._score_compliance(trace, skill_config)

        assert score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_compliance_llm_error(self):
        """LLM raises exception → 1.0 (fail-open: assume compliant)."""
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
        evaluator = Evaluator(llm_gateway=llm)
        skill_config = make_skill_config(output_format="JSON")
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator._score_compliance(trace, skill_config)

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_compliance_score_clamped_to_range(self):
        """LLM returns value outside range → clamped to [0.0, 1.0]."""
        llm = make_llm_gateway("1.5")
        evaluator = Evaluator(llm_gateway=llm)
        skill_config = make_skill_config(output_format="JSON")
        trace = make_trace(success=True, output_events=[{"event_type": "done"}])

        score = await evaluator._score_compliance(trace, skill_config)

        assert score == pytest.approx(1.0)


# ── Test: score_trace with skill_config ──────────────────────────────────────


class TestScoreTraceWithSkillConfig:
    """score_trace integrates compliance as a 4th signal."""

    @pytest.mark.asyncio
    async def test_score_trace_with_skill_config_all_signals(self):
        """All 4 signals combined: structural, semantic, compliance, human."""
        llm = make_llm_gateway("1.0")
        evaluator = Evaluator(llm_gateway=llm)
        skill_config = make_skill_config(output_format="JSON")
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "done"}],
            human_rating=5,
        )

        score = await evaluator.score_trace(trace, skill_config=skill_config)

        # structural=1.0, semantic=1.0, compliance=1.0, human=1.0 → 1.0
        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_score_trace_backwards_compatible(self):
        """score_trace(trace) with no skill_config still works as before."""
        llm = make_llm_gateway("1.0")
        evaluator = Evaluator(llm_gateway=llm)
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "done"}],
            human_rating=5,
        )

        # Old call signature — no skill_config
        score = await evaluator.score_trace(trace)

        # structural=1.0, semantic=1.0, compliance=1.0 (no format), human=1.0
        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_score_trace_no_human_with_skill_config(self):
        """No human rating with skill_config: average of 3 auto signals."""
        llm = make_llm_gateway("1.0")
        evaluator = Evaluator(llm_gateway=llm)
        skill_config = make_skill_config(output_format="JSON")
        trace = make_trace(
            success=True,
            output_events=[{"event_type": "done"}],
            human_rating=None,
        )

        score = await evaluator.score_trace(trace, skill_config=skill_config)

        # structural=1.0, semantic=1.0, compliance=1.0 → (1+1+1)/3 = 1.0
        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_score_trace_compliance_penalizes_no_output(self):
        """When output_format defined but no outputs, compliance=0.0 pulls score down."""
        llm = make_llm_gateway("1.0")
        evaluator = Evaluator(llm_gateway=llm)
        skill_config = make_skill_config(output_format="JSON")
        # success=True but no output_events → structural=0.5, compliance=0.0
        trace = make_trace(
            success=True,
            output_events=[],
            human_rating=None,
        )

        score = await evaluator.score_trace(trace, skill_config=skill_config)

        # structural=0.5, semantic=1.0 (LLM), compliance=0.0 → (0.5+1.0+0.0)/3
        assert score == pytest.approx(0.5)


# ── Test: default weights ─────────────────────────────────────────────────────


class TestDefaultWeights:
    """Default weights should include compliance and sum to 1.0."""

    def test_weights_include_compliance(self):
        """Default weights dict has 'compliance' key."""
        evaluator = Evaluator()

        assert "compliance" in evaluator._weights

    def test_weights_sum_to_one(self):
        """Default weights must sum to exactly 1.0."""
        evaluator = Evaluator()

        total = sum(evaluator._weights.values())

        assert total == pytest.approx(1.0)

    def test_all_expected_keys_present(self):
        """Default weights contain all 4 signal keys."""
        evaluator = Evaluator()

        assert set(evaluator._weights.keys()) == {
            "structural",
            "semantic",
            "compliance",
            "human",
        }
