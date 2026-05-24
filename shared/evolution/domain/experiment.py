"""Experiment aggregate for self-evolution canary rollouts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from shared.evolution.models import ExperimentStatus

ExperimentRolloutDecision = Literal["promote", "rollback", "continue"]

MAX_CANDIDATE_TRAFFIC_PCT = 30
DEFAULT_MIN_SAMPLES = 50
DEFAULT_MIN_IMPROVEMENT = 0.05


class InvalidEvolutionExperimentError(ValueError):
    """Raised when an experiment record cannot support domain decisions."""


@dataclass(frozen=True, slots=True)
class ExperimentRouteDecision:
    """Deterministic arm assignment for one trace inside an experiment."""

    experiment_id: str
    bucket: int
    is_candidate: bool
    skill_version: int


@dataclass(frozen=True, slots=True)
class ExperimentScoreSummary:
    """Score statistics used for canary rollout decisions."""

    control_scores: tuple[float, ...]
    candidate_scores: tuple[float, ...]
    min_samples: int
    min_improvement: float

    @property
    def control_count(self) -> int:
        return len(self.control_scores)

    @property
    def candidate_count(self) -> int:
        return len(self.candidate_scores)

    @property
    def has_min_samples(self) -> bool:
        return (
            self.control_count >= self.min_samples
            and self.candidate_count >= self.min_samples
        )

    @property
    def control_mean(self) -> float:
        if not self.control_scores:
            return 0.0
        return sum(self.control_scores) / len(self.control_scores)

    @property
    def candidate_mean(self) -> float:
        if not self.candidate_scores:
            return 0.0
        return sum(self.candidate_scores) / len(self.candidate_scores)

    @property
    def degradation(self) -> float:
        return (self.control_mean - self.candidate_mean) / max(
            self.control_mean,
            0.01,
        )


@dataclass(slots=True)
class EvolutionExperiment:
    """Aggregate root for a mini-canary skill experiment."""

    record: Any

    @classmethod
    def from_record(cls, record: Any) -> EvolutionExperiment:
        return cls(record=record)

    @staticmethod
    def normalize_traffic_pct(value: Any) -> int:
        traffic_pct = _coerce_int(value, fallback=10)
        return min(max(traffic_pct, 0), MAX_CANDIDATE_TRAFFIC_PCT)

    @staticmethod
    def normalize_min_samples(value: Any) -> int:
        return max(_coerce_int(value, fallback=DEFAULT_MIN_SAMPLES), 1)

    @staticmethod
    def normalize_min_improvement(value: Any) -> float:
        return max(_coerce_float(value, fallback=DEFAULT_MIN_IMPROVEMENT), 0.0)

    @property
    def experiment_id(self) -> str:
        return _required_text(_field(self.record, "experiment_id"), "experiment_id")

    @property
    def skill_id(self) -> str:
        return _required_text(_field(self.record, "skill_id"), "skill_id")

    @property
    def status(self) -> str:
        status = _field(self.record, "status", ExperimentStatus.RUNNING)
        if isinstance(status, ExperimentStatus):
            return status.value
        return str(status)

    @property
    def is_running(self) -> bool:
        return self.status == ExperimentStatus.RUNNING.value

    @property
    def control_version(self) -> int:
        return _coerce_int(_field(self.record, "control_version"), fallback=0)

    @property
    def candidate_version(self) -> int:
        return _coerce_int(_field(self.record, "candidate_version"), fallback=0)

    @property
    def traffic_pct(self) -> int:
        return max(_coerce_int(_field(self.record, "traffic_pct", 10), fallback=10), 0)

    @property
    def min_samples(self) -> int:
        return self.normalize_min_samples(
            _field(self.record, "min_samples", DEFAULT_MIN_SAMPLES)
        )

    @property
    def min_improvement(self) -> float:
        return self.normalize_min_improvement(
            _field(self.record, "min_improvement", DEFAULT_MIN_IMPROVEMENT)
        )

    def route(self, *, bucket: int) -> ExperimentRouteDecision:
        """Assign one deterministic bucket to the candidate or control arm."""
        _validate_bucket(bucket)
        is_candidate = bucket < self.traffic_pct
        return ExperimentRouteDecision(
            experiment_id=self.experiment_id,
            bucket=bucket,
            is_candidate=is_candidate,
            skill_version=self.candidate_version if is_candidate else self.control_version,
        )

    def score_summary(
        self,
        *,
        min_samples_override: int | None = None,
    ) -> ExperimentScoreSummary:
        """Return immutable score statistics for rollout decisions."""
        return ExperimentScoreSummary(
            control_scores=_score_tuple(_field(self.record, "control_results", ())),
            candidate_scores=_score_tuple(
                _field(self.record, "candidate_results", ())
            ),
            min_samples=(
                self.normalize_min_samples(min_samples_override)
                if min_samples_override is not None
                else self.min_samples
            ),
            min_improvement=self.min_improvement,
        )

    def canary_rollout_decision(
        self,
        *,
        min_samples_override: int | None = None,
        rollback_degradation_threshold: float = 0.10,
    ) -> ExperimentRolloutDecision:
        """Decide a simple canary route outcome for the router."""
        summary = self.score_summary(min_samples_override=min_samples_override)
        if not summary.has_min_samples:
            return "continue"
        if summary.candidate_mean >= summary.control_mean:
            return "promote"
        if summary.degradation > rollback_degradation_threshold:
            return "rollback"
        return "continue"

    def optimizer_rollout_decision(
        self,
        *,
        rollback_degradation_threshold: float = 0.10,
    ) -> ExperimentRolloutDecision:
        """Decide a skill-optimizer rollout using the experiment's threshold."""
        summary = self.score_summary()
        if not summary.has_min_samples:
            return "continue"
        if summary.candidate_mean >= summary.control_mean + summary.min_improvement:
            return "promote"
        if summary.degradation > rollback_degradation_threshold:
            return "rollback"
        return "continue"

    def status_for_decision(self, decision: ExperimentRolloutDecision) -> str:
        if decision == "promote":
            return ExperimentStatus.PROMOTED.value
        if decision == "rollback":
            return ExperimentStatus.ROLLED_BACK.value
        return ExperimentStatus.RUNNING.value


def _field(record: Any, name: str, default: Any = None) -> Any:
    return getattr(record, name, default)


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InvalidEvolutionExperimentError(f"{field_name} must not be empty")
    return text


def _coerce_int(value: Any, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback


def _coerce_float(value: Any, *, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


def _score_tuple(value: Any) -> tuple[float, ...]:
    if not value:
        return ()
    return tuple(_coerce_float(score, fallback=0.0) for score in value)


def _validate_bucket(bucket: int) -> None:
    if bucket < 0 or bucket >= 100:
        raise InvalidEvolutionExperimentError("bucket must be in [0, 100)")


__all__ = [
    "DEFAULT_MIN_IMPROVEMENT",
    "DEFAULT_MIN_SAMPLES",
    "MAX_CANDIDATE_TRAFFIC_PCT",
    "EvolutionExperiment",
    "ExperimentRouteDecision",
    "ExperimentRolloutDecision",
    "ExperimentScoreSummary",
    "InvalidEvolutionExperimentError",
]
