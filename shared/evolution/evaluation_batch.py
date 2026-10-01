"""Pure contracts and comparison rules for a fixed evolution evaluation batch.

These reports describe the supplied evaluation cases only. They are not live
model benchmarks and perform no sampling, model calls, persistence, or routing.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenContract(BaseModel):
    """Immutable, strict base for evaluation batch contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EvalCase(FrozenContract):
    """One versioned case in a fixed synthetic or private evaluation set."""

    case_id: str = Field(min_length=1, max_length=200)
    case_revision: str = Field(min_length=1, max_length=100)
    expects_policy_denial: bool = False


class EvalResult(FrozenContract):
    """Aggregate outcome for one case, including every attempt and retry cost."""

    result_id: str = Field(min_length=1, max_length=200)
    case_id: str = Field(min_length=1, max_length=200)
    config_revision: str = Field(min_length=1, max_length=200)
    accepted: bool
    quality: float = Field(ge=0.0, le=1.0)
    total_attempt_cost_usd: float = Field(ge=0.0)
    latency_ms: float = Field(ge=0.0)
    human_interventions: int = Field(ge=0)
    policy_denied: bool = False
    policy_violation: bool = False

    @field_validator("quality", "total_attempt_cost_usd", "latency_ms")
    @classmethod
    def _finite_number(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value


class EvaluationBatch(FrozenContract):
    """One arm's results for an immutable evaluation-set and config revision."""

    evaluation_id: str = Field(min_length=1, max_length=200)
    dataset_revision: str = Field(min_length=1, max_length=200)
    config_revision: str = Field(min_length=1, max_length=200)
    budget_usd: float = Field(ge=0.0)
    cases: tuple[EvalCase, ...]
    results: tuple[EvalResult, ...]

    @field_validator("budget_usd")
    @classmethod
    def _finite_budget(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("budget_usd must be finite")
        return value

    @model_validator(mode="after")
    def _validate_identifiers(self) -> EvaluationBatch:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique within a batch")
        result_ids = [result.result_id for result in self.results]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("result_id values must be unique within a batch")
        if len([result.case_id for result in self.results]) != len(
            {result.case_id for result in self.results}
        ):
            raise ValueError("each case may have at most one aggregate result")
        case_id_set = set(case_ids)
        for result in self.results:
            if result.case_id not in case_id_set:
                raise ValueError("result references a case outside the batch")
            if result.config_revision != self.config_revision:
                raise ValueError("result config_revision must match its batch")
        return self


class EvaluationPolicy(FrozenContract):
    """Declared promotion gates applied to both arms and their comparison."""

    minimum_sample_count: int = Field(default=1, ge=1)
    minimum_candidate_accepted_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    maximum_cost_per_accepted_outcome_usd: float = Field(ge=0.0)
    maximum_total_attempt_cost_usd: float | None = Field(default=None, ge=0.0)

    @field_validator(
        "minimum_candidate_accepted_quality",
        "maximum_cost_per_accepted_outcome_usd",
        "maximum_total_attempt_cost_usd",
    )
    @classmethod
    def _finite_threshold(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("threshold values must be finite")
        return value


class WilsonInterval(FrozenContract):
    """95% Wilson score interval; bounds are absent when the arm has no cases."""

    lower: float | None
    upper: float | None


class ArmEvaluationMetrics(FrozenContract):
    """Aggregated evidence for one arm of the same-budget comparison."""

    evaluation_id: str
    config_revision: str
    sample_count: int
    accepted_count: int
    accepted_outcome_rate: float | None
    accepted_outcome_rate_95_ci: WilsonInterval
    mean_accepted_quality: float
    total_attempt_cost_usd: float
    cost_per_accepted_outcome_usd: float | None
    mean_latency_ms: float
    total_human_interventions: int
    policy_denial_count: int
    policy_denial_failures: int
    policy_violation_count: int


class EvaluationComparison(FrozenContract):
    """Promotion eligibility plus per-arm evidence and stable reason codes."""

    eligible: bool
    reasons: tuple[str, ...]
    baseline: ArmEvaluationMetrics
    candidate: ArmEvaluationMetrics
    dataset_revision: str | None
    budget_usd: float | None
    report_kind: Literal["fixed_evaluation_case_comparison"] = "fixed_evaluation_case_comparison"
    is_live_model_benchmark: Literal[False] = False


def compare_evaluations(
    baseline: EvaluationBatch,
    candidate: EvaluationBatch,
    policy: EvaluationPolicy,
) -> EvaluationComparison:
    """Compare two fixed batches and return deterministic promotion gates.

    A result's ``total_attempt_cost_usd`` must include its failed attempts and
    retries. Both arms must use the same case revisions and declared budget.
    """

    baseline_metrics = _aggregate(baseline)
    candidate_metrics = _aggregate(candidate)
    reasons: list[str] = []

    baseline_cases = _case_signature(baseline)
    candidate_cases = _case_signature(candidate)
    if baseline.dataset_revision != candidate.dataset_revision or baseline_cases != candidate_cases:
        reasons.append("evaluation_cases_mismatch")
    if baseline.budget_usd != candidate.budget_usd:
        reasons.append("budget_mismatch")
    if baseline_metrics.total_attempt_cost_usd > baseline.budget_usd:
        reasons.append("baseline_budget_exceeded")
    if candidate_metrics.total_attempt_cost_usd > candidate.budget_usd:
        reasons.append("candidate_budget_exceeded")
    if baseline.config_revision == candidate.config_revision:
        reasons.append("config_revisions_must_differ")
    if {result.case_id for result in baseline.results} != {case.case_id for case in baseline.cases}:
        reasons.append("baseline_evaluation_incomplete")
    if {result.case_id for result in candidate.results} != {
        case.case_id for case in candidate.cases
    }:
        reasons.append("candidate_evaluation_incomplete")
    if candidate_metrics.mean_accepted_quality < baseline_metrics.mean_accepted_quality:
        reasons.append("candidate_quality_regression")

    if baseline_metrics.sample_count < policy.minimum_sample_count:
        reasons.append("baseline_sample_count_below_minimum")
    if candidate_metrics.sample_count < policy.minimum_sample_count:
        reasons.append("candidate_sample_count_below_minimum")
    if baseline_metrics.policy_violation_count:
        reasons.append("baseline_policy_violations")
    if candidate_metrics.policy_violation_count:
        reasons.append("candidate_policy_violations")
    if candidate_metrics.mean_accepted_quality < policy.minimum_candidate_accepted_quality:
        reasons.append("candidate_quality_below_minimum")
    candidate_cost = candidate_metrics.cost_per_accepted_outcome_usd
    if candidate_cost is None:
        reasons.append("candidate_has_no_accepted_outcomes")
    elif candidate_cost > policy.maximum_cost_per_accepted_outcome_usd:
        reasons.append("candidate_cost_per_accepted_outcome_exceeds_maximum")
    if (
        policy.maximum_total_attempt_cost_usd is not None
        and candidate_metrics.total_attempt_cost_usd > policy.maximum_total_attempt_cost_usd
    ):
        reasons.append("candidate_total_attempt_cost_exceeds_maximum")

    return EvaluationComparison(
        eligible=not reasons,
        reasons=tuple(reasons),
        baseline=baseline_metrics,
        candidate=candidate_metrics,
        dataset_revision=(
            baseline.dataset_revision
            if baseline.dataset_revision == candidate.dataset_revision
            else None
        ),
        budget_usd=(baseline.budget_usd if baseline.budget_usd == candidate.budget_usd else None),
    )


def _case_signature(batch: EvaluationBatch) -> tuple[tuple[str, str, bool], ...]:
    return tuple(
        sorted(
            (case.case_id, case.case_revision, case.expects_policy_denial) for case in batch.cases
        )
    )


def _aggregate(batch: EvaluationBatch) -> ArmEvaluationMetrics:
    cases = {case.case_id: case for case in batch.cases}
    results = batch.results
    sample_count = len(results)
    accepted = [result for result in results if result.accepted]
    accepted_count = len(accepted)
    expected_denial_failures = sum(
        1
        for result in results
        if cases[result.case_id].expects_policy_denial and not result.policy_denied
    )
    policy_violations = sum(1 for result in results if result.policy_violation)
    total_cost = sum(result.total_attempt_cost_usd for result in results)
    rate = accepted_count / sample_count if sample_count else None
    interval = _wilson_interval(accepted_count, sample_count)

    return ArmEvaluationMetrics(
        evaluation_id=batch.evaluation_id,
        config_revision=batch.config_revision,
        sample_count=sample_count,
        accepted_count=accepted_count,
        accepted_outcome_rate=rate,
        accepted_outcome_rate_95_ci=interval,
        mean_accepted_quality=(
            sum(result.quality for result in accepted) / accepted_count if accepted_count else 0.0
        ),
        total_attempt_cost_usd=total_cost,
        cost_per_accepted_outcome_usd=(total_cost / accepted_count if accepted_count else None),
        mean_latency_ms=(
            sum(result.latency_ms for result in results) / sample_count if sample_count else 0.0
        ),
        total_human_interventions=sum(result.human_interventions for result in results),
        policy_denial_count=sum(1 for result in results if result.policy_denied),
        policy_denial_failures=expected_denial_failures,
        policy_violation_count=policy_violations + expected_denial_failures,
    )


def _wilson_interval(successes: int, samples: int) -> WilsonInterval:
    """Calculate the two-sided 95% Wilson score interval for a proportion."""

    if samples == 0:
        return WilsonInterval(lower=None, upper=None)
    z = 1.959963984540054
    proportion = successes / samples
    z_squared = z * z
    denominator = 1 + z_squared / samples
    center = (proportion + z_squared / (2 * samples)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / samples + z_squared / (4 * samples * samples))
        / denominator
    )
    return WilsonInterval(
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
    )


__all__ = [
    "ArmEvaluationMetrics",
    "EvalCase",
    "EvalResult",
    "EvaluationBatch",
    "EvaluationComparison",
    "EvaluationPolicy",
    "WilsonInterval",
    "compare_evaluations",
]
