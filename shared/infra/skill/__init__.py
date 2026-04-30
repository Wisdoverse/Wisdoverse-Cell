"""
Skill System - Extensible skill framework for message handling.

Provides a plugin-like architecture for defining and executing skills
that can be triggered by commands, patterns, or LLM intent recognition.
"""
from shared.infra.skill.base import BaseSkill, SkillParameter
from shared.infra.skill.executor import SkillExecutor
from shared.infra.skill.matcher import SkillMatcher
from shared.infra.skill.models import (
    Permission,
    SkillContext,
    SkillError,
    SkillMatch,
    SkillResult,
)
from shared.infra.skill.registry import SkillRegistry
from shared.infra.skill.service import SkillService

__all__ = [
    "BaseSkill",
    "Permission",
    "SkillContext",
    "SkillError",
    "SkillExecutor",
    "SkillMatch",
    "SkillMatcher",
    "SkillParameter",
    "SkillRegistry",
    "SkillResult",
    "SkillService",
]
