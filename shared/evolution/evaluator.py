"""
Multi-Signal Evaluator — combines structural, semantic, compliance, and human feedback signals.

Design principles:
- Structural signal: deterministic, based on success flag + output_events
- Semantic signal: LLM-powered quality assessment of input→output mapping
- Compliance signal: LLM-powered check of output_format adherence (SkillConfig)
- Human signal: normalized 1-5 rating from human reviewers
- Graceful fallback: LLM errors fall back to structural score or fail-open
- Never crashes the caller — all exceptions are handled internally
"""

from __future__ import annotations

from typing import Any, Optional

from shared.utils.logger import get_logger

logger = get_logger("evolution.evaluator")

_SEMANTIC_PROMPT_TEMPLATE = """\
You are evaluating AI agent output quality. Score from 0.0 to 1.0.

Input event type: {input_event_type}
Output event count: {output_count}
Execution success: {success}

Does this output make sense for the given input? Reply with ONLY a single float between 0.0 and 1.0."""


class Evaluator:
    """Multi-signal evaluation: structure + semantic + human feedback.

    Usage::

        evaluator = Evaluator(llm_gateway=llm)
        score = await evaluator.score_trace(trace)
        aggregate = await evaluator.aggregate_scores(traces)
    """

    def __init__(
        self,
        llm_gateway: Any = None,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self._llm = llm_gateway
        self._weights = weights or {
            "structural": 0.25,
            "semantic": 0.25,
            "compliance": 0.15,
            "human": 0.35,
        }

    # ── Public API ─────────────────────────────────────────────────────────

    async def score_trace(self, trace: Any, skill_config: Any = None) -> float:
        """Score a single execution trace 0.0-1.0.

        Combines structural, semantic, compliance, and human feedback signals:
        - If human_rating is absent: returns (structural + semantic + compliance) / 3
        - If human_rating is present: returns weighted sum of all four signals

        Args:
            trace: Object with attributes:
                - success (bool)
                - output_events (list)
                - error (str | None)
                - human_rating (int | None, 1-5)
                - input_event (dict)
            skill_config: Optional SkillConfig with output_format to check compliance.
                If None, compliance signal defaults to 1.0.

        Returns:
            Float score in [0.0, 1.0].
        """
        structural = self._score_structural(trace)
        semantic = await self._score_semantic(trace) if self._llm else structural
        compliance = await self._score_compliance(trace, skill_config)
        human = self._score_human(trace)

        if human is None:
            return (structural + semantic + compliance) / 3

        return (
            self._weights.get("structural", 0.0) * structural
            + self._weights.get("semantic", 0.0) * semantic
            + self._weights.get("compliance", 0.0) * compliance
            + self._weights.get("human", 0.0) * human
        )

    async def aggregate_scores(self, traces: list[Any]) -> float:
        """Average score across traces.

        Args:
            traces: List of trace objects.

        Returns:
            Average score in [0.0, 1.0], or 0.0 if traces is empty.
        """
        if not traces:
            return 0.0

        scores = [await self.score_trace(t) for t in traces]
        return sum(scores) / len(scores)

    # ── Scoring signals ────────────────────────────────────────────────────

    def _score_structural(self, trace: Any) -> float:
        """Deterministic structural score based on success flag and output presence.

        Returns:
            1.0 if success and has output_events,
            0.5 if success but no output_events,
            0.0 if not success.
        """
        if not trace.success:
            return 0.0
        if trace.output_events:
            return 1.0
        return 0.5

    async def _score_semantic(self, trace: Any) -> float:
        """Ask LLM to assess whether the output makes sense for the input.

        Uses temperature=0 and max_tokens=10 for a focused, deterministic answer.
        Falls back to structural score on any error (LLM unavailable, parse failure).

        Returns:
            Float in [0.0, 1.0].
        """
        structural_fallback = self._score_structural(trace)

        input_event_type = ""
        if isinstance(trace.input_event, dict):
            input_event_type = trace.input_event.get("event_type", "unknown")

        prompt = _SEMANTIC_PROMPT_TEMPLATE.format(
            input_event_type=input_event_type,
            output_count=len(trace.output_events) if trace.output_events else 0,
            success=trace.success,
        )

        try:
            raw = await self._llm.complete(
                prompt=prompt,
                agent_id="evolution-evaluator",
                task_type="semantic_score",
                temperature=0,
                max_tokens=10,
            )
            return float(raw.strip())
        except Exception as exc:
            logger.warning(
                "evaluator.semantic_fallback",
                error=str(exc),
                fallback_score=structural_fallback,
            )
            return structural_fallback

    async def _score_compliance(
        self, trace: Any, skill_config: Any = None
    ) -> float:
        """Check if output follows the skill's expected output format.

        Returns:
            1.0 if output matches format or no format defined.
            0.0-1.0 based on LLM assessment of format compliance.
            Falls back to 1.0 if no LLM or no skill_config (fail-open).
        """
        if skill_config is None or not skill_config.output_format:
            return 1.0  # No format constraint = fully compliant

        if not trace.output_events:
            return 0.0  # No output = not compliant

        if self._llm is None:
            return 1.0  # Can't check without LLM

        prompt = (
            f"Rate how well this output complies with the expected format.\n"
            f"Expected format: {skill_config.output_format}\n"
            f"Output events count: {len(trace.output_events)}\n"
            f"Execution success: {trace.success}\n"
            f"Reply with ONLY a float between 0.0 and 1.0."
        )

        try:
            raw = await self._llm.complete(
                prompt=prompt,
                agent_id="evolution-evaluator",
                task_type="compliance_score",
                temperature=0,
                max_tokens=10,
            )
            return max(0.0, min(1.0, float(raw.strip())))
        except Exception:
            return 1.0  # Fail-open: assume compliant if can't check

    def _score_human(self, trace: Any) -> Optional[float]:
        """Normalize human_rating (1-5) to 0.0-1.0.

        Returns:
            Normalized float in [0.0, 1.0], or None if no rating provided.
        """
        if trace.human_rating is None:
            return None
        return (trace.human_rating - 1) / 4
