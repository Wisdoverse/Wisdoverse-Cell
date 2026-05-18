"""SQLAlchemy adapter for Evolution skill seed persistence."""

from collections.abc import Sequence

from shared.evolution.db.database import EvolutionDatabaseManager
from shared.evolution.db.repository import EvolutionRepository
from shared.evolution.models import SkillConfig

from ..core.seed_ports import EvolutionSkillSeedStore


class SqlAlchemyEvolutionSkillSeedStore(EvolutionSkillSeedStore):
    """SQLAlchemy-backed skill seed bootstrap store."""

    def __init__(self, db_manager: EvolutionDatabaseManager):
        self._db_manager = db_manager

    async def seed_missing_active_skills(
        self,
        seeds: Sequence[SkillConfig],
    ) -> int:
        if not seeds:
            return 0

        async with self._db_manager.session() as session:
            repo = EvolutionRepository(session)
            seeded = 0
            for seed in seeds:
                existing = await repo.get_active_skill(seed.skill_id)
                if existing is not None:
                    continue
                await repo.save_skill_config(
                    skill_id=seed.skill_id,
                    version=str(seed.version),
                    status=seed.status,
                    system_prompt=seed.system_prompt,
                    parameters=seed.parameters,
                    few_shot_examples=seed.few_shot_examples,
                    output_format=seed.output_format or "",
                    target_model=seed.target_model or "",
                )
                seeded += 1
            return seeded
