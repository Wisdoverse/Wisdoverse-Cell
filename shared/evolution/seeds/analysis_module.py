"""
Seed SkillConfig entries for Analysis Module.

Source files:
  - shared/capabilities/analysis/core/daily_report.py
  - shared/capabilities/analysis/core/weekly_report.py
  - shared/capabilities/analysis/core/milestone_checker.py
  - shared/capabilities/analysis/core/quality_evaluator.py

The Analysis Module does NOT make direct LLM calls; it generates reports
from BiTable data using deterministic logic.  The seed list is empty.
"""

from shared.evolution.models import SkillConfig

ANALYSIS_MODULE_SEEDS: list[SkillConfig] = []
