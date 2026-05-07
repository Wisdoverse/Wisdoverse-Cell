"""
Seed SkillConfig entries for Sync Module.

Source files:
  - shared/capabilities/sync/core/engine.py
  - shared/capabilities/sync/service/agent.py

The Sync Module performs deterministic OpenProject <-> Feishu data
synchronization and does NOT make direct LLM calls.  The seed list is empty.
"""

from shared.evolution.models import SkillConfig

SYNC_MODULE_SEEDS: list[SkillConfig] = []
