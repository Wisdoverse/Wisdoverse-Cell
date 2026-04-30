"""Tests for CanaryRouter — deterministic traffic splitting for mini-canary experiments.

TDD: written before implementation.
"""

import hashlib
from unittest.mock import AsyncMock

import pytest

from shared.evolution.canary_router import CanaryRouter


def _make_bucket(trace_id: str) -> int:
    """Helper: reproduce the same bucket logic used by CanaryRouter."""
    return int(hashlib.md5(trace_id.encode()).hexdigest()[:8], 16) % 100


def _make_experiment(
    experiment_id: str = "exp-001",
    control_version: int = 1,
    candidate_version: int = 2,
    traffic_pct: int = 10,
) -> AsyncMock:
    """Return a mock Experiment object."""
    exp = AsyncMock()
    exp.experiment_id = experiment_id
    exp.control_version = control_version
    exp.candidate_version = candidate_version
    exp.traffic_pct = traffic_pct
    return exp


def _make_skill(version: int = 3) -> AsyncMock:
    """Return a mock SkillConfig object."""
    skill = AsyncMock()
    skill.version = version
    return skill


class TestResolveSkillVersionNoExperiment:
    """When no experiment is running, returns active skill version or default."""

    @pytest.mark.asyncio
    async def test_no_experiment_returns_active_skill_version(self):
        """Returns the active skill's version when no experiment is running."""
        repo = AsyncMock()
        repo.get_active_experiment.return_value = None
        repo.get_active_skill.return_value = _make_skill(version=5)

        router = CanaryRouter(repo=repo)
        version = await router.resolve_skill_version(
            agent_id="pjm-agent", skill_id="summarize", trace_id="trace-abc"
        )

        assert version == 5
        repo.get_active_experiment.assert_called_once_with("pjm-agent", "summarize")
        repo.get_active_skill.assert_called_once_with("summarize")

    @pytest.mark.asyncio
    async def test_no_experiment_no_active_skill_returns_default_1(self):
        """Returns 1 (default) when no experiment and no active skill exists."""
        repo = AsyncMock()
        repo.get_active_experiment.return_value = None
        repo.get_active_skill.return_value = None

        router = CanaryRouter(repo=repo)
        version = await router.resolve_skill_version(
            agent_id="pjm-agent", skill_id="summarize", trace_id="trace-xyz"
        )

        assert version == 1


class TestResolveSkillVersionWithExperiment:
    """When an experiment is running, routing is deterministic via MD5 hash."""

    @pytest.mark.asyncio
    async def test_experiment_routes_to_candidate_when_bucket_below_traffic_pct(self):
        """trace_id whose bucket < traffic_pct routes to candidate_version."""
        # Find a trace_id whose bucket is 0 (always below any traffic_pct > 0)
        # We can brute-force a trace_id that hashes to bucket 0
        trace_id = "trace-000"
        bucket = _make_bucket(trace_id)
        # Use traffic_pct larger than bucket to ensure candidate routing
        traffic_pct = bucket + 1  # guaranteed to route to candidate

        repo = AsyncMock()
        repo.get_active_experiment.return_value = _make_experiment(
            control_version=1, candidate_version=2, traffic_pct=traffic_pct
        )

        router = CanaryRouter(repo=repo)
        version = await router.resolve_skill_version(
            agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id
        )

        assert version == 2  # candidate

    @pytest.mark.asyncio
    async def test_experiment_routes_to_control_when_bucket_at_or_above_traffic_pct(self):
        """trace_id whose bucket >= traffic_pct routes to control_version."""
        trace_id = "trace-000"
        bucket = _make_bucket(trace_id)
        # Use traffic_pct equal to bucket so bucket >= traffic_pct
        traffic_pct = bucket  # bucket == traffic_pct → control

        repo = AsyncMock()
        repo.get_active_experiment.return_value = _make_experiment(
            control_version=1, candidate_version=2, traffic_pct=traffic_pct
        )

        router = CanaryRouter(repo=repo)
        version = await router.resolve_skill_version(
            agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id
        )

        assert version == 1  # control

    @pytest.mark.asyncio
    async def test_routing_is_deterministic_same_trace_id_always_same_version(self):
        """Calling resolve_skill_version 10 times with same trace_id always returns same version."""
        trace_id = "stable-trace-id-12345"
        repo = AsyncMock()
        repo.get_active_experiment.return_value = _make_experiment(
            control_version=1, candidate_version=2, traffic_pct=10
        )

        router = CanaryRouter(repo=repo)

        versions = [
            await router.resolve_skill_version(
                agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id
            )
            for _ in range(10)
        ]

        # All must be identical
        assert len(set(versions)) == 1, f"Expected deterministic result, got {versions}"

    @pytest.mark.asyncio
    async def test_traffic_distribution_approximately_proportional(self):
        """With traffic_pct=10, ~10% of 1000 unique trace_ids route to candidate."""
        repo = AsyncMock()
        repo.get_active_experiment.return_value = _make_experiment(
            control_version=1, candidate_version=2, traffic_pct=10
        )

        router = CanaryRouter(repo=repo)

        candidate_count = 0
        total = 1000
        for i in range(total):
            trace_id = f"trace-{i:05d}"
            version = await router.resolve_skill_version(
                agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id
            )
            if version == 2:
                candidate_count += 1

        # Expect approximately 10% ± 3% tolerance
        ratio = candidate_count / total
        assert 0.07 <= ratio <= 0.13, (
            f"Expected ~10% candidate traffic, got {ratio:.1%} ({candidate_count}/{total})"
        )


class TestRecordResult:
    """record_result() appends scores to the correct experiment arm."""

    @pytest.mark.asyncio
    async def test_no_experiment_returns_without_recording(self):
        """If no active experiment, record_result returns silently without DB call."""
        repo = AsyncMock()
        repo.get_active_experiment.return_value = None

        router = CanaryRouter(repo=repo)
        await router.record_result(
            agent_id="pjm-agent", skill_id="summarize", trace_id="trace-abc", score=0.9
        )

        repo.add_experiment_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_result_routes_to_candidate_arm(self):
        """trace_id hashing to bucket < traffic_pct records as candidate (is_candidate=True)."""
        trace_id = "trace-000"
        bucket = _make_bucket(trace_id)
        traffic_pct = bucket + 1  # candidate

        repo = AsyncMock()
        repo.get_active_experiment.return_value = _make_experiment(
            experiment_id="exp-canary-1",
            traffic_pct=traffic_pct,
        )

        router = CanaryRouter(repo=repo)
        await router.record_result(
            agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id, score=0.85
        )

        repo.add_experiment_result.assert_called_once_with(
            "exp-canary-1", is_candidate=True, score=0.85
        )

    @pytest.mark.asyncio
    async def test_record_result_routes_to_control_arm(self):
        """trace_id hashing to bucket >= traffic_pct records as control (is_candidate=False)."""
        trace_id = "trace-000"
        bucket = _make_bucket(trace_id)
        traffic_pct = bucket  # control (bucket == traffic_pct)

        repo = AsyncMock()
        repo.get_active_experiment.return_value = _make_experiment(
            experiment_id="exp-canary-2",
            traffic_pct=traffic_pct,
        )

        router = CanaryRouter(repo=repo)
        await router.record_result(
            agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id, score=0.75
        )

        repo.add_experiment_result.assert_called_once_with(
            "exp-canary-2", is_candidate=False, score=0.75
        )

    @pytest.mark.asyncio
    async def test_record_result_consistent_with_resolve_skill_version(self):
        """record_result routing is consistent with resolve_skill_version for same trace_id."""
        trace_id = "consistent-trace-999"
        bucket = _make_bucket(trace_id)

        repo = AsyncMock()
        # Use traffic_pct > bucket so we expect candidate routing
        traffic_pct = min(bucket + 1, 30)
        exp = _make_experiment(
            experiment_id="exp-consistency",
            control_version=1,
            candidate_version=2,
            traffic_pct=traffic_pct,
        )
        repo.get_active_experiment.return_value = exp

        router = CanaryRouter(repo=repo)

        resolved_version = await router.resolve_skill_version(
            agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id
        )
        await router.record_result(
            agent_id="pjm-agent", skill_id="summarize", trace_id=trace_id, score=1.0
        )

        call_kwargs = repo.add_experiment_result.call_args
        is_candidate_recorded = call_kwargs.kwargs["is_candidate"]

        if resolved_version == 2:  # candidate
            assert is_candidate_recorded is True
        else:  # control
            assert is_candidate_recorded is False
