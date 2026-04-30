"""
Seed SkillConfig entries extracted from Chat Agent hardcoded prompts.

Source files:
  - agents/chat_agent/core/chat_service.py  (PM_PERSONA_PROMPT, default system, summarize)

These seeds represent the v1 baseline for self-evolution tracking.
The Chat Agent code itself is NOT modified — these are read-only copies.
"""

from shared.evolution.models import SkillConfig, SkillStatus

# ---------------------------------------------------------------------------
# Skill 1: PM Persona Chat
# ---------------------------------------------------------------------------
# Extracted from: agents/chat_agent/core/chat_service.py  PM_PERSONA_PROMPT

CHAT_PM_PERSONA_SKILL = SkillConfig(
    skill_id="chat-agent:pm-persona",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "你是 Wisdoverse Cell 的 AI 项目管理助手，具备 CEO 思维和全局视角。\n"
        "\n"
        "## 核心能力\n"
        "- **闭环思维**：给出解决方案和明确的行动建议，不只是记录问题\n"
        "- **确定性**：提前预警风险，提供 Plan B，给出确定的判断\n"
        "- **商业视角**：结合项目目标给出建议，关注商业价值和 ROI\n"
        "- **信息枢纽**：把技术问题翻译成业务影响\n"
        "\n"
        "## 回答风格\n"
        "- 简洁有力，直击要点，先结论后分析\n"
        "- 使用 Markdown 格式化输出（加粗、列表、代码块等）\n"
        "- 提供可执行的行动项，量化影响\n"
        "- 用中文回答"
    ),
    parameters={
        "max_tokens": 4096,
        "temperature": 0,
    },
    target_model="claude-sonnet-4-20250514",
)

# ---------------------------------------------------------------------------
# Skill 2: Default Chat
# ---------------------------------------------------------------------------
# Extracted from: agents/chat_agent/core/chat_service.py  default_system

CHAT_DEFAULT_SKILL = SkillConfig(
    skill_id="chat-agent:default-chat",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "你是一个项目管理助手，可以帮助用户查询项目任务、更新进度、管理飞书表格、"
        "执行同步、搜索用户并发送消息。"
        "当需要数据时，请主动使用工具获取实时信息。请用简洁、专业的中文回答。"
    ),
    parameters={
        "max_tokens": 4096,
        "temperature": 0,
    },
    target_model="claude-sonnet-4-20250514",
)

# ---------------------------------------------------------------------------
# Skill 3: Conversation Summarization
# ---------------------------------------------------------------------------
# Extracted from: agents/chat_agent/core/chat_service.py  _summarize_history()

CHAT_SUMMARIZE_SKILL = SkillConfig(
    skill_id="chat-agent:summarize",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt="你是一个对话摘要助手。请用 2-3 句话概括以下对话的关键信息和结论。",
    parameters={
        "max_tokens": 300,
        "temperature": 0,
    },
    target_model="claude-haiku-4-5-20251001",
)

# ---------------------------------------------------------------------------
# All Chat Agent seeds
# ---------------------------------------------------------------------------

CHAT_AGENT_SEEDS: list[SkillConfig] = [
    CHAT_PM_PERSONA_SKILL,
    CHAT_DEFAULT_SKILL,
    CHAT_SUMMARIZE_SKILL,
]
