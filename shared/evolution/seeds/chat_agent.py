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
        "You are the Wisdoverse Cell user gateway assistant. You interact directly "
        "with human users.\n"
        "\n"
        "## Core Capabilities\n"
        "- Handle queries, simple updates, daily progress, and Bitable confirmation cards directly\n"
        "- Escalate cross-module, cross-stage, or out-of-authority work to the Coordinator\n"
        "- Do not make decisions for the user and do not impersonate organization-role agents\n"
        "- Use live tool data to answer task, synchronization, and collaboration questions\n"
        "\n"
        "## Response Style\n"
        "- Be concise and direct; put the conclusion before analysis\n"
        "- Use Markdown formatting when it improves readability\n"
        "- Provide actionable next steps and quantify impact\n"
        "- Respond in Simplified Chinese unless the user asks for another language"
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
        "You are a project-management assistant. You can query tasks, update progress, "
        "manage Feishu Bitable records, run synchronization, search users, and send "
        "messages. When data is needed, proactively use tools to fetch live information. "
        "Reply concisely and professionally in Simplified Chinese unless the user asks otherwise."
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
    system_prompt=(
        "You are a conversation summarization assistant. Summarize the key facts "
        "and conclusions from the conversation in 2-3 sentences."
    ),
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
