"""Application use cases for Evolution skill seed bootstrap."""
from __future__ import annotations

from collections.abc import Sequence

from shared.evolution.models import SkillConfig
from shared.utils.logger import get_logger

from .seed_ports import EvolutionSkillSeedStore

logger = get_logger("evolution_module.seed_bootstrap")


class EvolutionSeedBootstrapUseCase:
    """Idempotently bootstrap Evolution skill seeds outside the service shell."""

    def __init__(
        self,
        *,
        seed_store: EvolutionSkillSeedStore,
        seeds: Sequence[SkillConfig] | None = None,
    ) -> None:
        self._seed_store = seed_store
        self._seeds = seeds

    async def bootstrap(self) -> int:
        try:
            all_seeds = list(
                default_evolution_skill_seeds()
                if self._seeds is None
                else self._seeds
            )
            if not all_seeds:
                return 0

            seeded = await self._seed_store.seed_missing_active_skills(all_seeds)
            if seeded:
                logger.info("skill_seeds_bootstrapped", count=seeded)
            return seeded
        except Exception as exc:
            logger.warning(
                "skill_seed_bootstrap_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return 0


def default_evolution_skill_seeds() -> list[SkillConfig]:
    """Return the built-in Evolution skill seed catalog."""
    from shared.evolution.seeds.chat_agent import CHAT_AGENT_SEEDS
    from shared.evolution.seeds.pjm_agent import PM_AGENT_SEEDS
    from shared.evolution.seeds.requirement_manager import REQUIREMENT_MANAGER_SEEDS

    return [
        *PM_AGENT_SEEDS,
        *CHAT_AGENT_SEEDS,
        *REQUIREMENT_MANAGER_SEEDS,
    ]
