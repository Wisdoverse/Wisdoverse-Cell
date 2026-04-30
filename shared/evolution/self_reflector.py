"""
SelfReflector — half-auto LLM-powered analysis of execution traces.

Analyses a batch of ExecutionTrace records and generates a Reflection
containing success/failure patterns and optimization suggestions for
human review.

Design principles:
- Only summarized data is sent to LLM (no raw trace IDs / PII)
- Returns None on any error — never crashes the caller
- Uses temperature=0.2 for more deterministic output
"""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, Any, Optional

from shared.evolution.models import Reflection
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger("evolution.reflector")

_PROMPT_TEMPLATE = """\
You are an AI system optimizer. Analyze the following execution statistics for an agent skill and provide a JSON optimization report.

Agent: {agent_id}
Skill: {skill_id}

## Execution Statistics
- Total traces: {total}
- Successes: {success_count}
- Failures: {failure_count}
- Success rate: {success_rate:.1%}
- Average human rating: {avg_rating}
- Rated traces count: {rated_count}

## Failure Summary (grouped by error message)
{failure_summary}

## Human Corrections (up to 5 examples)
{corrections_summary}

## Current Skill Configuration
- System prompt length: {prompt_len} chars
- Parameter names: {param_names}
- Few-shot examples count: {few_shot_count}
{reflection_chain_section}
## Task
Based on the above statistics, produce a JSON object with the following keys:
- "success_patterns": list[str] — what is working well
- "failure_patterns": list[str] — recurring failure modes
- "optimization_suggestions": list[str] — concrete, actionable improvements
- "human_corrections_summary": str — synthesize the human correction examples into one concise summary

Output ONLY valid JSON with no additional text or markdown.
"""

_REFLECTION_CHAIN_TEMPLATE = """\

## Previous Reflection Chain ({chain_length} rounds)
{reflection_chain_summary}

IMPORTANT: Build on previous insights. Do NOT repeat the same suggestions that were already tried. Focus on NEW patterns and improvements.
"""


class SelfReflector:
    """Analyzes execution traces and generates LLM-powered optimization suggestions.

    Usage::

        reflector = SelfReflector(llm_gateway=llm)
        reflection = await reflector.reflect(
            agent_id="pjm-agent",
            skill_id="decompose-task",
            traces=recent_traces,
            current_skill=active_skill_config,
        )
        if reflection:
            await submit_for_human_review(reflection)
    """

    def __init__(self, llm_gateway: Any) -> None:
        self._llm = llm_gateway

    # ── Public API ────────────────────────────────────────────────────────

    async def reflect(
        self,
        agent_id: str,
        skill_id: str,
        traces: list[Any],
        current_skill: Any = None,
        previous_reflections: list[Any] | None = None,
    ) -> Optional[Reflection]:
        """Analyze *traces* and return a :class:`Reflection` for human review.

        Returns ``None`` if:
        - *traces* is empty
        - The LLM call fails for any reason
        - The LLM response cannot be parsed into a valid ``Reflection``
        """
        if not traces:
            logger.warning(
                "self_reflector.empty_traces",
                agent_id=agent_id,
                skill_id=skill_id,
            )
            return None

        try:
            prompt = self._build_prompt(
                agent_id, skill_id, traces, current_skill, previous_reflections
            )
            raw = await self._llm.complete(
                prompt=prompt,
                agent_id="evolution-reflector",
                task_type="self_reflect",
                max_tokens=2048,
                temperature=0.2,
            )
            return self._parse_response(agent_id, skill_id, raw)
        except Exception as exc:
            logger.error(
                "self_reflector.error",
                agent_id=agent_id,
                skill_id=skill_id,
                error=str(exc),
            )
            return None

    # ── Helpers ───────────────────────────────────────────────────────────

    def _summarize_failures(self, traces: list[Any]) -> str:
        """Group failure traces by error message and return a counted summary.

        Only the top 10 error types by frequency are included.
        Returns an empty string when there are no failures.
        """
        error_counts: Counter[str] = Counter()
        for t in traces:
            if not t.success and t.error:
                error_counts[t.error] += 1

        if not error_counts:
            return ""

        lines: list[str] = []
        for error_msg, count in error_counts.most_common(10):
            lines.append(f"  - {error_msg!r}: {count} occurrence(s)")
        return "\n".join(lines)

    def _summarize_corrections(self, corrections: list[str]) -> str:
        """Return a bullet-point list of up to 5 human correction texts.

        Returns an empty string when *corrections* is empty.
        """
        if not corrections:
            return ""

        capped = corrections[:5]
        lines = [f"  - {c}" for c in capped]
        return "\n".join(lines)

    # ── Private ───────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        agent_id: str,
        skill_id: str,
        traces: list[Any],
        current_skill: Any,
        previous_reflections: list[Any] | None = None,
    ) -> str:
        """Build the LLM prompt from summarized trace statistics."""
        total = len(traces)
        success_count = sum(1 for t in traces if t.success)
        failure_count = total - success_count
        success_rate = success_count / total if total > 0 else 0.0

        rated = [t for t in traces if t.human_rating is not None]
        rated_count = len(rated)
        avg_rating: str
        if rated_count > 0:
            avg = sum(t.human_rating for t in rated) / rated_count
            avg_rating = f"{avg:.2f} / 5 (n={rated_count})"
        else:
            avg_rating = "N/A (no ratings)"

        failure_summary = self._summarize_failures(traces) or "  None"

        corrections = [
            t.human_correction
            for t in traces
            if t.human_correction is not None
        ]
        corrections_summary = self._summarize_corrections(corrections) or "  None"

        # Current skill config stats (optional)
        prompt_len = 0
        param_names = "N/A"
        few_shot_count = 0
        if current_skill is not None:
            prompt_len = len(current_skill.system_prompt or "")
            params = current_skill.parameters or {}
            param_names = ", ".join(params.keys()) if params else "none"
            few_shot_count = len(current_skill.few_shot_examples or [])

        # Previous reflection chain section (optional)
        reflection_chain_section = ""
        if previous_reflections:
            reflection_chain_section = self._build_reflection_chain(
                previous_reflections
            )

        return _PROMPT_TEMPLATE.format(
            agent_id=agent_id,
            skill_id=skill_id,
            total=total,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            avg_rating=avg_rating,
            rated_count=rated_count,
            failure_summary=failure_summary,
            corrections_summary=corrections_summary,
            prompt_len=prompt_len,
            param_names=param_names,
            few_shot_count=few_shot_count,
            reflection_chain_section=reflection_chain_section,
        )

    def _build_reflection_chain(self, previous_reflections: list[Any]) -> str:
        """Summarize previous reflections into a chain string for the LLM prompt.

        Caps at the 5 most recent reflections.  Each field is truncated to
        ~200 characters to keep the prompt concise.
        """
        _MAX_REFLECTIONS = 5
        _MAX_FIELD_LEN = 200

        capped = previous_reflections[:_MAX_REFLECTIONS]
        lines: list[str] = []

        for i, ref in enumerate(capped):
            round_num = len(capped) - i  # most recent = highest round
            date_str = ""
            created_at = getattr(ref, "created_at", None)
            if created_at is not None:
                try:
                    date_str = created_at.strftime("%Y-%m-%d")
                except Exception:
                    pass

            label = f"Round {round_num}"
            if date_str:
                label = f"{label} ({date_str})"

            def _fmt(items: Any) -> str:
                if not items:
                    return "none"
                text = "; ".join(str(x) for x in items)
                return text[:_MAX_FIELD_LEN] + "..." if len(text) > _MAX_FIELD_LEN else text

            lines.append(f"{label}:")
            lines.append(f"  - Success patterns: {_fmt(getattr(ref, 'success_patterns', []))}")
            lines.append(f"  - Failure patterns: {_fmt(getattr(ref, 'failure_patterns', []))}")
            lines.append(f"  - Suggestions: {_fmt(getattr(ref, 'optimization_suggestions', []))}")

        chain_summary = "\n".join(lines)
        return _REFLECTION_CHAIN_TEMPLATE.format(
            chain_length=len(capped),
            reflection_chain_summary=chain_summary,
        )

    def _parse_response(
        self,
        agent_id: str,
        skill_id: str,
        raw: str,
    ) -> Optional[Reflection]:
        """Parse LLM JSON response into a :class:`Reflection`.

        Returns ``None`` on JSON or validation errors.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                "self_reflector.json_parse_error",
                agent_id=agent_id,
                skill_id=skill_id,
                error=str(exc),
                raw_preview=raw[:200],
            )
            return None

        # Inject identifiers so the model can validate the full Reflection
        data["agent_id"] = agent_id
        data["skill_id"] = skill_id

        try:
            return Reflection.model_validate(data)
        except Exception as exc:
            logger.error(
                "self_reflector.validation_error",
                agent_id=agent_id,
                skill_id=skill_id,
                error=str(exc),
            )
            return None
