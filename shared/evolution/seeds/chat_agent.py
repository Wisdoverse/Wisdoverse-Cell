"""
Seed SkillConfig entries extracted from the user interaction gateway prompts.

Source files:
  - agents/gateways/user_interaction/core/chat_service.py

These seeds represent the v1 baseline for self-evolution tracking.
The Chat Agent code itself is NOT modified — these are read-only copies.
"""

from shared.evolution.models import SkillConfig, SkillStatus

# ---------------------------------------------------------------------------
# Skill 1: User Assistant Chat
# ---------------------------------------------------------------------------
# Extracted from: agents/gateways/user_interaction/core/chat_service.py

CHAT_USER_ASSISTANT_SKILL = SkillConfig(
    skill_id="chat-agent:user-assistant",
    version=1,
    status=SkillStatus.ACTIVE,
    system_prompt=(
        "你是 Wisdoverse Cell 的用户助手，直接面对人类用户，用中文交流。\n"
        "\n"
        "## 核心能力\n"
        "- 直接处理查询、简单更新、每日进展和多维表格确认卡片\n"
        "- 将跨模块、跨阶段或超出权限的工作升级给 Coordinator\n"
        "- 不代替用户做决定，不伪装成组织角色 agent\n"
        "- 用实时工具数据回答任务、同步和协作问题\n"
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
# Extracted from: agents/gateways/user_interaction/core/chat_service.py

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
# Extracted from: agents/gateways/user_interaction/core/chat_service.py

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
    CHAT_USER_ASSISTANT_SKILL,
    CHAT_DEFAULT_SKILL,
    CHAT_SUMMARIZE_SKILL,
]
