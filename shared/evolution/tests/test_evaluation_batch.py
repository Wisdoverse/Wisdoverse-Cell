"""Tests for deterministic fixed-case evolution evaluation comparisons."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.evolution.evaluation_batch import (
    EvalCase,
    EvalResult,
    EvaluationBatch,
    EvaluationPolicy,
    compare_evaluations,
)


def _batch(
    *,
    evaluation_id: str,
    config_revision: str,
    results: tuple[EvalResult, ...],
    cases: tuple[EvalCase, ...] | None = None,
    budget_usd: float = 10.0,
) -> EvaluationBatch:
    return EvaluationBatch(
        evaluation_id=evaluation_id,
        dataset_revision="synthetic-v1",
        config_revision=config_revision,
        budget_usd=budget_usd,
        cases=cases or (EvalCase(case_id="case-1", case_revision="1"),),
        results=results,
    )


def _result(
    *,
    result_id: str,
    case_id: str = "case-1",
    config_revision: str,
    accepted: bool = True,
    quality: float = 0.9,
    cost: float = 1.0,
    latency_ms: float = 100.0,
    human_interventions: int = 0,
    policy_denied: bool = False,
    policy_violation: bool = False,
) -> EvalResult:
    return EvalResult(
        result_id=result_id,
        case_id=case_id,
        config_revision=config_revision,
        accepted=accepted,
        quality=quality,
        total_attempt_cost_usd=cost,
        latency_ms=latency_ms,
        human_interventions=human_interventions,
        policy_denied=policy_denied,
        policy_violation=policy_violation,
    )


def _eligible_policy(**overrides) -> EvaluationPolicy:
    values = {
        "minimum_sample_count": 1,
        "minimum_candidate_accepted_quality": 0.8,
        "maximum_cost_per_accepted_outcome_usd": 5.0,
    }
    values.update(overrides)
    return EvaluationPolicy(**values)


def test_unreported_policy_case_blocks_comparison_even_when_samples_meet_minimum() -> None:
    cases = (
        EvalCase(case_id="case-1", case_revision="1"),
        EvalCase(case_id="denied", case_revision="1", expects_policy_denial=True),
    )
    baseline = _batch(
        evaluation_id="baseline",
        config_revision="v1",
        cases=cases,
        results=(_result(result_id="b", config_revision="v1"),),
    )
    candidate = _batch(
        evaluation_id="candidate",
        config_revision="v2",
        cases=cases,
        results=(_result(result_id="c", config_revision="v2"),),
    )
    comparison = compare_evaluations(baseline, candidate, _eligible_policy())
    assert not comparison.eligible
    assert "baseline_evaluation_incomplete" in comparison.reasons
    assert "candidate_evaluation_incomplete" in comparison.reasons


def test_quality_regression_blocks_candidate_above_declared_minimum() -> None:
    baseline = _batch(
        evaluation_id="baseline",
        config_revision="v1",
        results=(_result(result_id="b", config_revision="v1", quality=0.95),),
    )
    candidate = _batch(
        evaluation_id="candidate",
        config_revision="v2",
        results=(_result(result_id="c", config_revision="v2", quality=0.85),),
    )
    comparison = compare_evaluations(baseline, candidate, _eligible_policy())
    assert not comparison.eligible
    assert "candidate_quality_regression" in comparison.reasons


def test_failed_attempt_and_retry_cost_is_included_in_cost_per_accepted_outcome() -> None:
    cases = (
        EvalCase(case_id="case-1", case_revision="1"),
        EvalCase(case_id="case-2", case_revision="1"),
    )
    baseline = _batch(
        evaluation_id="baseline-eval",
        config_revision="skill-v1",
        cases=cases,
        results=(
            _result(result_id="b-1", config_revision="skill-v1", cost=2),
            _result(
                result_id="b-2",
                case_id="case-2",
                config_revision="skill-v1",
                accepted=False,
                cost=3,
            ),
        ),
    )
    candidate = _batch(
        evaluation_id="candidate-eval",
        config_revision="skill-v2",
        cases=cases,
        results=(
            _result(result_id="c-1", config_revision="skill-v2", cost=2),
            _result(
                result_id="c-2",
                case_id="case-2",
                config_revision="skill-v2",
                accepted=False,
                # This aggregate includes a failed first attempt and a retry.
                cost=7,
            ),
        ),
    )

    comparison = compare_evaluations(baseline, candidate, _eligible_policy())

    assert comparison.candidate.total_attempt_cost_usd == 9
    assert comparison.candidate.cost_per_accepted_outcome_usd == 9
    assert comparison.candidate.accepted_count == 1
    assert comparison.candidate.policy_denial_failures == 0
    assert comparison.is_live_model_benchmark is False


def test_zero_accepted_outcomes_have_null_cost_and_block_promotion() -> None:
    baseline = _batch(
        evaluation_id="baseline-eval",
        config_revision="v1",
        results=(_result(result_id="b", config_revision="v1"),),
    )
    candidate = _batch(
        evaluation_id="candidate-eval",
        config_revision="v2",
        results=(
            _result(
                result_id="c",
                config_revision="v2",
                accepted=False,
                quality=0.0,
                cost=4.0,
            ),
        ),
    )

    comparison = compare_evaluations(baseline, candidate, _eligible_policy())

    assert comparison.candidate.cost_per_accepted_outcome_usd is None
    assert comparison.candidate.accepted_outcome_rate == 0
    assert "candidate_has_no_accepted_outcomes" in comparison.reasons
    assert not comparison.eligible


def test_case_or_config_revision_mismatch_blocks_comparison() -> None:
    baseline = _batch(
        evaluation_id="baseline-eval",
        config_revision="v1",
        cases=(EvalCase(case_id="case-1", case_revision="1"),),
        results=(_result(result_id="b", config_revision="v1"),),
    )
    candidate = _batch(
        evaluation_id="candidate-eval",
        config_revision="v1",
        cases=(EvalCase(case_id="case-1", case_revision="2"),),
        results=(_result(result_id="c", config_revision="v1"),),
    )

    comparison = compare_evaluations(baseline, candidate, _eligible_policy())

    assert "evaluation_cases_mismatch" in comparison.reasons
    assert "config_revisions_must_differ" in comparison.reasons
    assert comparison.dataset_revision == "synthetic-v1"
    assert not comparison.eligible


def test_expected_policy_denial_failure_blocks_promotion() -> None:
    cases = (EvalCase(case_id="case-1", case_revision="1", expects_policy_denial=True),)
    baseline = _batch(
        evaluation_id="baseline-eval",
        config_revision="v1",
        cases=cases,
        results=(
            _result(
                result_id="b",
                config_revision="v1",
                accepted=False,
                policy_denied=True,
            ),
        ),
    )
    candidate = _batch(
        evaluation_id="candidate-eval",
        config_revision="v2",
        cases=cases,
        results=(_result(result_id="c", config_revision="v2"),),
    )

    comparison = compare_evaluations(baseline, candidate, _eligible_policy())

    assert comparison.candidate.policy_denial_failures == 1
    assert comparison.candidate.policy_violation_count == 1
    assert "candidate_policy_violations" in comparison.reasons


def test_explicit_policy_violation_blocks_promotion() -> None:
    baseline = _batch(
        evaluation_id="baseline-eval",
        config_revision="v1",
        results=(_result(result_id="b", config_revision="v1"),),
    )
    candidate = _batch(
        evaluation_id="candidate-eval",
        config_revision="v2",
        results=(
            _result(
                result_id="c",
                config_revision="v2",
                policy_violation=True,
            ),
        ),
    )

    comparison = compare_evaluations(baseline, candidate, _eligible_policy())

    assert comparison.candidate.policy_violation_count == 1
    assert "candidate_policy_violations" in comparison.reasons


def test_declared_quality_cost_and_sample_thresholds_are_enforced() -> None:
    baseline = _batch(
        evaluation_id="baseline-eval",
        config_revision="v1",
        results=(_result(result_id="b", config_revision="v1"),),
    )
    candidate = _batch(
        evaluation_id="candidate-eval",
        config_revision="v2",
        results=(
            _result(
                result_id="c",
                config_revision="v2",
                quality=0.6,
                cost=8,
                human_interventions=2,
            ),
        ),
    )

    comparison = compare_evaluations(
        baseline,
        candidate,
        _eligible_policy(
            minimum_sample_count=2,
            minimum_candidate_accepted_quality=0.7,
            maximum_cost_per_accepted_outcome_usd=5,
            maximum_total_attempt_cost_usd=7,
        ),
    )

    assert "candidate_sample_count_below_minimum" in comparison.reasons
    assert "candidate_quality_below_minimum" in comparison.reasons
    assert "candidate_cost_per_accepted_outcome_exceeds_maximum" in comparison.reasons
    assert "candidate_total_attempt_cost_exceeds_maximum" in comparison.reasons
    assert comparison.candidate.total_human_interventions == 2
    assert comparison.candidate.mean_latency_ms == 100


def test_wilson_interval_edge_values_and_empty_arm() -> None:
    empty = _batch(
        evaluation_id="empty",
        config_revision="v1",
        results=(),
    )
    all_success = _batch(
        evaluation_id="success",
        config_revision="v2",
        results=(_result(result_id="s", config_revision="v2"),),
    )
    all_failure = _batch(
        evaluation_id="failure",
        config_revision="v3",
        results=(
            _result(
                result_id="f",
                config_revision="v3",
                accepted=False,
                quality=0,
            ),
        ),
    )

    empty_comparison = compare_evaluations(empty, all_success, _eligible_policy())
    success_comparison = compare_evaluations(all_failure, all_success, _eligible_policy())
    failure_comparison = compare_evaluations(all_success, all_failure, _eligible_policy())

    assert empty_comparison.baseline.accepted_outcome_rate is None
    assert empty_comparison.baseline.accepted_outcome_rate_95_ci.lower is None
    assert empty_comparison.baseline.accepted_outcome_rate_95_ci.upper is None
    assert success_comparison.candidate.accepted_outcome_rate_95_ci.lower == pytest.approx(
        0.20654931437723745
    )
    assert success_comparison.candidate.accepted_outcome_rate_95_ci.upper == 1
    assert failure_comparison.candidate.accepted_outcome_rate_95_ci.lower == 0
    assert failure_comparison.candidate.accepted_outcome_rate_95_ci.upper == pytest.approx(
        0.7934506856227626
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("quality", float("nan")),
        ("quality", float("inf")),
        ("total_attempt_cost_usd", -0.01),
        ("latency_ms", -1),
        ("human_interventions", -1),
    ],
)
def test_result_rejects_invalid_numeric_values(field: str, value: float) -> None:
    payload = {
        "result_id": "r1",
        "case_id": "case-1",
        "config_revision": "v1",
        "accepted": True,
        "quality": 0.8,
        "total_attempt_cost_usd": 1,
        "latency_ms": 100,
        "human_interventions": 0,
        field: value,
    }

    with pytest.raises(ValidationError):
        EvalResult.model_validate(payload)
