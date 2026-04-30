from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.evolution.canary_router import CanaryRouter


@pytest.mark.asyncio
async def test_promote_when_candidate_wins():
    experiment = MagicMock()
    experiment.experiment_id = "exp-1"
    experiment.min_samples = 10
    experiment.control_results = [0.8, 0.7, 0.9, 0.8, 0.7, 0.8, 0.9, 0.7, 0.8, 0.9]
    experiment.candidate_results = [0.9, 0.9, 0.95, 0.9, 0.85, 0.9, 0.95, 0.9, 0.85, 0.9]

    repo = AsyncMock()
    repo.get_active_experiment = AsyncMock(return_value=experiment)
    repo.conclude_experiment = AsyncMock()

    router = CanaryRouter(repo=repo)
    result = await router.check_experiment("agent-1", "skill-1")

    assert result == "promote"
    repo.conclude_experiment.assert_called_once_with("exp-1", status="promoted")


@pytest.mark.asyncio
async def test_rollback_when_candidate_much_worse():
    experiment = MagicMock()
    experiment.experiment_id = "exp-2"
    experiment.min_samples = 10
    experiment.control_results = [0.9, 0.9, 0.85, 0.9, 0.9, 0.85, 0.9, 0.9, 0.85, 0.9]
    experiment.candidate_results = [0.3, 0.4, 0.2, 0.3, 0.4, 0.2, 0.3, 0.4, 0.2, 0.3]

    repo = AsyncMock()
    repo.get_active_experiment = AsyncMock(return_value=experiment)
    repo.conclude_experiment = AsyncMock()

    router = CanaryRouter(repo=repo)
    result = await router.check_experiment("agent-1", "skill-1")

    assert result == "rollback"
    repo.conclude_experiment.assert_called_once_with("exp-2", status="rolled_back")


@pytest.mark.asyncio
async def test_continue_when_insufficient_data():
    experiment = MagicMock()
    experiment.experiment_id = "exp-3"
    experiment.min_samples = 10
    experiment.control_results = [0.8, 0.9]
    experiment.candidate_results = [0.85]

    repo = AsyncMock()
    repo.get_active_experiment = AsyncMock(return_value=experiment)

    router = CanaryRouter(repo=repo)
    result = await router.check_experiment("agent-1", "skill-1")
    assert result == "continue"


@pytest.mark.asyncio
async def test_no_experiment():
    repo = AsyncMock()
    repo.get_active_experiment = AsyncMock(return_value=None)

    router = CanaryRouter(repo=repo)
    result = await router.check_experiment("agent-1", "skill-1")
    assert result == "no_experiment"


@pytest.mark.asyncio
async def test_continue_when_slight_degradation():
    """Candidate slightly worse (<10% drop) should continue, not rollback."""
    experiment = MagicMock()
    experiment.experiment_id = "exp-4"
    experiment.min_samples = 10
    experiment.control_results = [0.90] * 10
    experiment.candidate_results = [0.85] * 10  # ~5.6% drop, under 10% threshold

    repo = AsyncMock()
    repo.get_active_experiment = AsyncMock(return_value=experiment)

    router = CanaryRouter(repo=repo)
    result = await router.check_experiment("agent-1", "skill-1")
    assert result == "continue"
