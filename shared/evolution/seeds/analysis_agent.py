"""
Seed SkillConfig entries for Analysis Agent.

Source files:
  - agents/analysis_agent/core/daily_report.py
  - agents/analysis_agent/core/weekly_report.py
  - agents/analysis_agent/core/milestone_checker.py
  - agents/analysis_agent/core/quality_evaluator.py

The Analysis Agent does NOT make direct LLM calls; it generates reports
from BiTable data using deterministic logic.  The seed list is empty.
"""

from shared.evolution.models import SkillConfig

ANALYSIS_AGENT_SEEDS: list[SkillConfig] = []
