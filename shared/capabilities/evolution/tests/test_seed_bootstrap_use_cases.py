import pytest

from shared.capabilities.evolution.core.seed_bootstrap_use_cases import (
    EvolutionSeedBootstrapUseCase,
    default_evolution_skill_seeds,
)
from shared.evolution.models import SkillConfig


class FakeSeedStore:
    def __init__(self, *, seeded: int = 0, error: Exception | None = None):
        self.seeded = seeded
        self.error = error
        self.seeds: list[SkillConfig] = []

    async def seed_missing_active_skills(self, seeds):
        if self.error is not None:
            raise self.error
        self.seeds = list(seeds)
        return self.seeded


def _seed(skill_id: str = "pjm-agent:decompose") -> SkillConfig:
    return SkillConfig(
        skill_id=skill_id,
        version=1,
        system_prompt="Decompose work items.",
    )


@pytest.mark.asyncio
async def test_bootstrap_persists_configured_seeds() -> None:
    store = FakeSeedStore(seeded=1)
    use_case = EvolutionSeedBootstrapUseCase(
        seed_store=store,
        seeds=[_seed()],
    )

    result = await use_case.bootstrap()

    assert result == 1
    assert [seed.skill_id for seed in store.seeds] == ["pjm-agent:decompose"]


@pytest.mark.asyncio
async def test_bootstrap_skips_empty_seed_catalog() -> None:
    store = FakeSeedStore(seeded=1)
    use_case = EvolutionSeedBootstrapUseCase(seed_store=store, seeds=[])

    result = await use_case.bootstrap()

    assert result == 0
    assert store.seeds == []


@pytest.mark.asyncio
async def test_bootstrap_handles_store_failure_as_startup_degradation() -> None:
    store = FakeSeedStore(error=RuntimeError("database down"))
    use_case = EvolutionSeedBootstrapUseCase(
        seed_store=store,
        seeds=[_seed()],
    )

    result = await use_case.bootstrap()

    assert result == 0


def test_default_evolution_skill_seeds_include_runtime_agents() -> None:
    skill_ids = {seed.skill_id for seed in default_evolution_skill_seeds()}

    assert "pjm-agent:decompose" in skill_ids
    assert "requirement-manager:extraction" in skill_ids
