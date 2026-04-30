"""
HelpSkill - Displays all available skills in the system.

This skill provides a help menu showing all registered skills,
their descriptions, and trigger commands.
"""
from typing import Callable, Optional

from shared.infra.skill import BaseSkill, Permission, SkillContext, SkillResult
from shared.messaging.inbound import AgentResponse, UnifiedCard


class HelpSkill(BaseSkill):
    """Displays all available skills."""

    name = "help"
    description = "显示所有可用技能"
    commands = ["/help", "/skills"]
    patterns = [r"有什么技能", r"能做什么", r"帮助"]
    permissions = [Permission.GATEWAY_REPLY]

    def __init__(self, skill_list_provider: Optional[Callable[[], list[BaseSkill]]] = None):
        """Initialize HelpSkill.

        Args:
            skill_list_provider: A callable that returns list of skills.
                This allows HelpSkill to access the registry without
                circular imports. Typically provided by SkillRegistry.
        """
        self._skill_list_provider = skill_list_provider

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the help skill to display available skills.

        Args:
            context: Skill execution context.

        Returns:
            SkillResult with a card listing all available skills.
        """
        # Get skill list from provider if available
        skills = self._skill_list_provider() if self._skill_list_provider else []

        # Format skill info
        lines = ["**可用技能:**\n"]
        for skill in skills:
            cmds = ", ".join(skill.commands) if skill.commands else "无"
            lines.append(f"- **{skill.name}**: {skill.description}")
            lines.append(f"  命令: {cmds}")

        if not skills:
            lines = ["暂无可用技能"]

        content = "\n".join(lines)

        return SkillResult(
            success=True,
            response=AgentResponse(
                card=UnifiedCard(
                    title="帮助 - 可用技能",
                    content=content,
                )
            ),
        )
