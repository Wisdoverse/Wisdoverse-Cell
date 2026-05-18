"""Ports for evolution capability skill seed persistence."""

from collections.abc import Sequence
from typing import Protocol

from shared.evolution.models import SkillConfig


class EvolutionSkillSeedStore(Protocol):
    """Persistence port for idempotent skill seed bootstrap."""

    async def seed_missing_active_skills(
        self,
        seeds: Sequence[SkillConfig],
    ) -> int:
        """Persist active skill seeds that do not already have an active row."""
