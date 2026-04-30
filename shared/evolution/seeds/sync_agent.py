"""
Seed SkillConfig entries for Sync Agent.

Source files:
  - agents/sync_agent/core/engine.py
  - agents/sync_agent/service/agent.py

The Sync Agent performs deterministic OpenProject <-> Feishu data
synchronization and does NOT make direct LLM calls.  The seed list is empty.
"""

from shared.evolution.models import SkillConfig

SYNC_AGENT_SEEDS: list[SkillConfig] = []
