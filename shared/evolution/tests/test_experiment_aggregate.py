"""Unit tests for the self-evolution experiment aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from shared.evolution.domain import (
    EvolutionExperiment,
    InvalidEvolutionExperimentError,
)


@dataclass
class ExperimentRecord:
    experiment_id: str = "exp-001"
    skill_id: str = "decompose-task"
    status: str = "running"
    control_version: int = 1
    candidate_version: int = 2
    traffic_pct: int = 10
    min_samples: int = 3
    min_improvement: float = 0.05
    control_results: list[float] = field(default_factory=list)
    candidate_results: list[float] = field(default_factory=list)


def test_routes_bucket_to_candidate_or_control_version() -> None:
    aggregate = EvolutionExperiment.from_record(ExperimentRecord(traffic_pct=10))

    candidate = aggregate.route(bucket=9)
    control = aggregate.route(bucket=10)

    assert candidate.is_candidate is True
    assert candidate.skill_version == 2
    assert control.is_candidate is False
    assert control.skill_version == 1


def test_route_rejects_invalid_bucket() -> None:
    aggregate = EvolutionExperiment.from_record(ExperimentRecord())

    with pytest.raises(InvalidEvolutionExperimentError):
        aggregate.route(bucket=100)


def test_new_experiment_traffic_percentage_is_capped_to_domain_limit() -> None:
    assert EvolutionExperiment.normalize_traffic_pct(90) == 30
    assert EvolutionExperiment.normalize_traffic_pct(-10) == 0


def test_score_summary_requires_both_experiment_arms() -> None:
    aggregate = EvolutionExperiment.from_record(
        ExperimentRecord(
            min_samples=3,
            control_results=[0.8, 0.9, 0.7],
            candidate_results=[0.9, 0.95],
        )
    )

    summary = aggregate.score_summary()

    assert summary.control_count == 3
    assert summary.candidate_count == 2
    assert summary.has_min_samples is False
    assert aggregate.optimizer_rollout_decision() == "continue"


def test_optimizer_promotes_only_when_min_improvement_is_met() -> None:
    aggregate = EvolutionExperiment.from_record(
        ExperimentRecord(
            min_samples=3,
            min_improvement=0.05,
            control_results=[0.80, 0.80, 0.80],
            candidate_results=[0.90, 0.90, 0.90],
        )
    )

    assert aggregate.optimizer_rollout_decision() == "promote"
    assert aggregate.status_for_decision("promote") == "promoted"


def test_optimizer_continues_when_candidate_wins_below_required_improvement() -> None:
    aggregate = EvolutionExperiment.from_record(
        ExperimentRecord(
            min_samples=3,
            min_improvement=0.05,
            control_results=[0.80, 0.80, 0.80],
            candidate_results=[0.83, 0.83, 0.83],
        )
    )

    assert aggregate.optimizer_rollout_decision() == "continue"


def test_canary_router_can_promote_without_optimizer_min_improvement() -> None:
    aggregate = EvolutionExperiment.from_record(
        ExperimentRecord(
            min_samples=3,
            min_improvement=0.05,
            control_results=[0.80, 0.80, 0.80],
            candidate_results=[0.83, 0.83, 0.83],
        )
    )

    assert aggregate.canary_rollout_decision() == "promote"


def test_rolls_back_when_candidate_degradation_exceeds_threshold() -> None:
    aggregate = EvolutionExperiment.from_record(
        ExperimentRecord(
            min_samples=3,
            control_results=[0.90, 0.90, 0.90],
            candidate_results=[0.70, 0.70, 0.70],
        )
    )

    assert aggregate.optimizer_rollout_decision() == "rollback"
    assert aggregate.status_for_decision("rollback") == "rolled_back"
