"""
Seed SkillConfig entries extracted from Requirement Manager Agent hardcoded prompts.

Source files:
  - agents/requirement_manager/core/extractor.py   (extraction system_prompt)
  - agents/requirement_manager/core/generator.py    (document_generation system_prompt)
  - agents/requirement_manager/core/analyzer.py     (analysis system_prompt)
  - agents/requirement_manager/core/comparator.py   (conflict_detection system_prompt)

These seeds represent the v1 baseline for self-evolution tracking.
The Requirement Manager code itself is NOT modified — these are read-only copies.
"""

from shared.evolution.models import SkillConfig, SkillStatus

# ---------------------------------------------------------------------------
# Skill 1: Requirement Extraction
# ---------------------------------------------------------------------------
# Extracted from: agents/requirement_manager/core/extractor.py

RM_EXTRACTION_SKILL = SkillConfig(
    skill_id="requirement-manager:extraction",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "You are a professional product requirements analyst. You are skilled "
        "at extracting structured requirements from meeting notes."
    ),
    parameters={
        "temperature": 0,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# Skill 2: Document Generation (PRD)
# ---------------------------------------------------------------------------
# Extracted from: agents/requirement_manager/core/generator.py

RM_DOCUMENT_GENERATION_SKILL = SkillConfig(
    skill_id="requirement-manager:document-generation",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "You are a professional technical documentation expert specialized in "
        "product requirements documents."
    ),
    parameters={
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# Skill 3: Requirement Analysis
# ---------------------------------------------------------------------------
# Extracted from: agents/requirement_manager/core/analyzer.py

RM_ANALYSIS_SKILL = SkillConfig(
    skill_id="requirement-manager:analysis",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "You are a requirements analysis expert. You are skilled at evaluating "
        "priority, complexity, dependencies, and risk."
    ),
    parameters={
        "temperature": 0,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# Skill 4: Conflict Detection
# ---------------------------------------------------------------------------
# Extracted from: agents/requirement_manager/core/comparator.py

RM_CONFLICT_DETECTION_SKILL = SkillConfig(
    skill_id="requirement-manager:conflict-detection",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "You are a professional requirements analysis expert. You are skilled "
        "at identifying relationships between requirements."
    ),
    parameters={
        "temperature": 0,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# All Requirement Manager seeds
# ---------------------------------------------------------------------------

REQUIREMENT_MANAGER_SEEDS: list[SkillConfig] = [
    RM_EXTRACTION_SKILL,
    RM_DOCUMENT_GENERATION_SKILL,
    RM_ANALYSIS_SKILL,
    RM_CONFLICT_DETECTION_SKILL,
]
