"""
Seed SkillConfig entries extracted from Requirement Manager Agent hardcoded prompts.

Source files:
  - agents/capabilities/requirements/core/extractor.py   (extraction system_prompt)
  - agents/capabilities/requirements/core/generator.py    (document_generation system_prompt)
  - agents/capabilities/requirements/core/analyzer.py     (analysis system_prompt)
  - agents/capabilities/requirements/core/comparator.py   (conflict_detection system_prompt)

These seeds represent the v1 baseline for self-evolution tracking.
The Requirement Manager code itself is NOT modified — these are read-only copies.
"""

from shared.evolution.models import SkillConfig, SkillStatus

# ---------------------------------------------------------------------------
# Skill 1: Requirement Extraction
# ---------------------------------------------------------------------------
# Extracted from: agents/capabilities/requirements/core/extractor.py

RM_EXTRACTION_SKILL = SkillConfig(
    skill_id="requirement-manager:extraction",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt="你是一个专业的产品需求分析师，精通从会议记录中提取结构化需求。",
    parameters={
        "temperature": 0,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# Skill 2: Document Generation (PRD)
# ---------------------------------------------------------------------------
# Extracted from: agents/capabilities/requirements/core/generator.py

RM_DOCUMENT_GENERATION_SKILL = SkillConfig(
    skill_id="requirement-manager:document-generation",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt="你是一个专业的技术文档专家，精通产品需求文档编写。",
    parameters={
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# Skill 3: Requirement Analysis
# ---------------------------------------------------------------------------
# Extracted from: agents/capabilities/requirements/core/analyzer.py

RM_ANALYSIS_SKILL = SkillConfig(
    skill_id="requirement-manager:analysis",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt="你是需求分析专家，擅长评估需求的优先级、复杂度和风险。",
    parameters={
        "temperature": 0,
    },
    target_model="claude-opus-4-6",
)

# ---------------------------------------------------------------------------
# Skill 4: Conflict Detection
# ---------------------------------------------------------------------------
# Extracted from: agents/capabilities/requirements/core/comparator.py

RM_CONFLICT_DETECTION_SKILL = SkillConfig(
    skill_id="requirement-manager:conflict-detection",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt="你是一个专业的需求分析专家，精通识别需求之间的关系。",
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
